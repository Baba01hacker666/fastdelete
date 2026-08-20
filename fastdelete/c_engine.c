/*
 * High-performance C deletion engine for fastdelete.
 * Uses direct POSIX streaming readdir(), unlink(), rmdir(), iterative stack traversal,
 * native C secure shredding, and high-speed disk space calculation.
 *
 * Notes on correctness:
 *  - Directory symlinks are NEVER followed: they are unlinked like files.
 *  - The traversal stack grows dynamically, so arbitrarily deep trees work.
 *  - Regular files are lstat'ed so bytes_deleted is accurate.
 *  - Force mode never chmod's through a symlink and also fixes the PARENT
 *    directory permissions, which is what actually gates unlink()/rmdir().
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <dirent.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <fcntl.h>
#include <errno.h>
#include <stdint.h>

typedef struct {
    uint64_t files_discovered;
    uint64_t files_deleted;
    uint64_t dirs_deleted;
    uint64_t bytes_deleted;
    uint64_t skipped;
    uint64_t failed;
    uint64_t symlinks_deleted;   /* append-only: keep in sync with _CDeleteStats (deleter.py) */
    uint64_t symlinks_skipped;
} CDeleteStats;

typedef struct {
    DIR *dirp;
    char *path;      /* malloc'd, owned by the frame */
    size_t path_len;
    int depth;
} StackFrame;

/* Attempt to make the parent directory of `path` writable. unlink()/rmdir()
 * succeed based on the parent's permissions, not the entry's own mode. */
static void try_fix_parent(const char *path) {
    const char *slash = strrchr(path, '/');
    char *parent;
    if (slash == NULL) {
        return;
    } else if (slash == path) {
        parent = strdup("/");
    } else {
        parent = strndup(path, (size_t)(slash - path));
    }
    if (!parent) return;

    struct stat st;
    if (lstat(parent, &st) == 0 && !S_ISLNK(st.st_mode)) {
        chmod(parent, st.st_mode | S_IWUSR | S_IXUSR | S_IRUSR);
    }
    free(parent);
}

/* Force permissions on a read-only file/dir. Never follows symlinks. */
static int try_force_chmod(const char *path, int is_dir) {
    struct stat st;
    if (lstat(path, &st) != 0 || S_ISLNK(st.st_mode)) {
        return -1;
    }
    mode_t new_mode = st.st_mode | S_IWUSR | S_IRUSR | (is_dir ? S_IXUSR : 0);
    return chmod(path, new_mode);
}

/* Unlink with optional force retry. Returns 0 if deleted or already gone. */
static int unlink_with_force(const char *path, int force, int is_lnk) {
    if (unlink(path) == 0) return 0;
    if (errno == ENOENT) return 0;
    if (!force) return -1;

    try_fix_parent(path);
    if (!is_lnk) {
        try_force_chmod(path, 0);
    }
    if (unlink(path) == 0 || errno == ENOENT) return 0;
    return -1;
}

/* Rmdir with optional force retry. Returns 0 if removed or already gone. */
static int rmdir_with_force(const char *path, int force) {
    if (rmdir(path) == 0) return 0;
    if (errno == ENOENT) return 0;
    int saved = errno;
    if (!force) { errno = saved; return -1; }

    try_fix_parent(path);
    try_force_chmod(path, 1);
    if (rmdir(path) == 0 || errno == ENOENT) return 0;
    errno = saved;
    return -1;
}

/* Secure file shredding in C */
int c_shred_file(const char *path, int passes, int method) {
    struct stat st;
    if (lstat(path, &st) != 0) return -1;
    if (S_ISLNK(st.st_mode)) {
        return unlink(path) == 0 ? 0 : -1;
    }
    if (S_ISDIR(st.st_mode)) return -1;

    off_t size = st.st_size;
    if (size == 0) {
        return unlink(path) == 0 ? 0 : -1;
    }

    int fd = open(path, O_WRONLY);
    if (fd < 0) {
        chmod(path, 0666);
        fd = open(path, O_WRONLY);
        if (fd < 0) return -1;
    }

    char buf[65536];
    int num_passes = (passes > 0) ? passes : 3;

    for (int p = 0; p < num_passes; p++) {
        lseek(fd, 0, SEEK_SET);
        if (method == 0) {
            /* Zero fill */
            memset(buf, 0, sizeof(buf));
        } else if (method == 1) {
            /* 0xFF fill */
            memset(buf, 0xFF, sizeof(buf));
        } else {
            /* Pseudo-random fill */
            for (size_t i = 0; i < sizeof(buf); i++) {
                buf[i] = (char)(rand() & 0xFF);
            }
        }

        off_t rem = size;
        while (rem > 0) {
            size_t chunk = (rem < (off_t)sizeof(buf)) ? (size_t)rem : sizeof(buf);
            ssize_t written = write(fd, buf, chunk);
            if (written <= 0) break;
            rem -= written;
        }
#if defined(_POSIX_SYNCHRONIZED_IO) && (_POSIX_SYNCHRONIZED_IO > 0)
        fdatasync(fd);
#else
        fsync(fd);
#endif
    }

    /* Truncate and sync */
    int tr_res = ftruncate(fd, 0);
    (void)tr_res;
    fsync(fd);
    close(fd);

    return unlink(path) == 0 ? 0 : -1;
}

/* Fast directory size calculation in C */
int c_calculate_dir_size(
    const char *target_path,
    uint64_t *out_bytes,
    uint64_t *out_files,
    uint64_t *out_dirs
) {
    if (!target_path || !out_bytes || !out_files || !out_dirs) return -1;
    *out_bytes = 0;
    *out_files = 0;
    *out_dirs = 0;

    struct stat root_st;
    if (lstat(target_path, &root_st) != 0) return -1;
    if (!S_ISDIR(root_st.st_mode) || S_ISLNK(root_st.st_mode)) {
        *out_files = 1;
        *out_bytes = S_ISREG(root_st.st_mode) ? root_st.st_size : 0;
        return 0;
    }

    size_t stack_cap = 64;
    int stack_ptr = -1;
    StackFrame *stack = (StackFrame *)malloc(sizeof(StackFrame) * stack_cap);
    if (!stack) return -2;

    DIR *root_dirp = opendir(target_path);
    if (!root_dirp) {
        free(stack);
        return -1;
    }

    stack_ptr = 0;
    stack[0].dirp = root_dirp;
    stack[0].path = strdup(target_path);
    stack[0].path_len = stack[0].path ? strlen(stack[0].path) : 0;
    stack[0].depth = 0;
    (*out_dirs)++;

    while (stack_ptr >= 0) {
        StackFrame *curr = &stack[stack_ptr];
        struct dirent *entry = readdir(curr->dirp);

        if (!entry) {
            closedir(curr->dirp);
            free(curr->path);
            stack_ptr--;
            continue;
        }

        if (entry->d_name[0] == '.' && (entry->d_name[1] == '\0' || (entry->d_name[1] == '.' && entry->d_name[2] == '\0'))) {
            continue;
        }

        size_t name_len = strlen(entry->d_name);
        size_t need = curr->path_len + 1 + name_len + 1;
        char *full_path = (char *)malloc(need);
        if (!full_path) continue;
        memcpy(full_path, curr->path, curr->path_len);
        full_path[curr->path_len] = '/';
        memcpy(full_path + curr->path_len + 1, entry->d_name, name_len);
        full_path[curr->path_len + 1 + name_len] = '\0';

        int is_dir = 0;
        if (entry->d_type == DT_DIR) {
            is_dir = 1;
        } else if (entry->d_type == DT_REG) {
            struct stat ent_st;
            if (lstat(full_path, &ent_st) == 0) {
                (*out_bytes) += ent_st.st_size;
            }
            (*out_files)++;
            free(full_path);
            continue;
        } else if (entry->d_type == DT_UNKNOWN) {
            struct stat ent_st;
            if (lstat(full_path, &ent_st) == 0) {
                if (S_ISDIR(ent_st.st_mode)) {
                    is_dir = 1;
                } else {
                    (*out_bytes) += ent_st.st_size;
                    (*out_files)++;
                    free(full_path);
                    continue;
                }
            } else {
                free(full_path);
                continue;
            }
        } else {
            /* symlink, fifo, socket */
            (*out_files)++;
            free(full_path);
            continue;
        }

        if (is_dir) {
            DIR *sub_dirp = opendir(full_path);
            if (!sub_dirp) {
                free(full_path);
                continue;
            }
            (*out_dirs)++;

            if ((size_t)(stack_ptr + 1) >= stack_cap) {
                size_t new_cap = stack_cap * 2;
                StackFrame *grown = (StackFrame *)realloc(stack, sizeof(StackFrame) * new_cap);
                if (!grown) {
                    closedir(sub_dirp);
                    free(full_path);
                    continue;
                }
                stack = grown;
                stack_cap = new_cap;
            }

            stack_ptr++;
            stack[stack_ptr].dirp = sub_dirp;
            stack[stack_ptr].path = full_path;
            stack[stack_ptr].path_len = strlen(full_path);
            stack[stack_ptr].depth = curr->depth + 1;
            continue;
        }
    }

    free(stack);
    return 0;
}

/* Single-threaded high-performance C tree deleter */
int c_fastdelete_tree(
    const char *target_path,
    int dry_run,
    int force,
    int one_file_system,
    int max_depth,
    int delete_root_dir,
    volatile int *abort_flag,
    CDeleteStats *stats_out
) {
    if (!target_path || !stats_out) return -1;
    memset(stats_out, 0, sizeof(CDeleteStats));

    if (abort_flag && *abort_flag) {
        return 0;
    }

    struct stat root_st;
    if (lstat(target_path, &root_st) != 0) {
        stats_out->failed++;
        return -1;
    }

    dev_t base_dev = root_st.st_dev;

    /* If target is not a directory or is a symlink: remove the single item
     * itself. Never follows the link. */
    if (!S_ISDIR(root_st.st_mode) || S_ISLNK(root_st.st_mode)) {
        stats_out->files_discovered++;
        if (dry_run) {
            stats_out->files_deleted++;
            if (S_ISLNK(root_st.st_mode)) stats_out->symlinks_deleted++;
            stats_out->bytes_deleted += S_ISREG(root_st.st_mode) ? root_st.st_size : 0;
            return 0;
        }
        int is_lnk = S_ISLNK(root_st.st_mode);
        if (unlink_with_force(target_path, force, is_lnk) == 0) {
            stats_out->files_deleted++;
            if (is_lnk) stats_out->symlinks_deleted++;
            stats_out->bytes_deleted += S_ISREG(root_st.st_mode) ? root_st.st_size : 0;
            return 0;
        }
        stats_out->failed++;
        return -1;
    }

    /* Target is a directory -> iterative post-order traversal with a
     * dynamically growing stack (no hardcoded depth limit). */
    size_t stack_cap = 64;
    int stack_ptr = -1;
    StackFrame *stack = (StackFrame *)malloc(sizeof(StackFrame) * stack_cap);
    if (!stack) return -2;

    DIR *root_dirp = opendir(target_path);
    if (!root_dirp) {
        free(stack);
        stats_out->failed++;
        return -1;
    }

    stack_ptr = 0;
    stack[0].dirp = root_dirp;
    stack[0].path = strdup(target_path);
    stack[0].path_len = stack[0].path ? strlen(stack[0].path) : 0;
    stack[0].depth = 0;
    if (!stack[0].path) {
        closedir(root_dirp);
        free(stack);
        return -2;
    }

    while (stack_ptr >= 0) {
        if (abort_flag && *abort_flag) {
            break;
        }

        StackFrame *curr = &stack[stack_ptr];
        errno = 0;
        struct dirent *entry = readdir(curr->dirp);

        if (!entry) {
            /* End of directory reached: close and remove directory (post-order) */
            closedir(curr->dirp);
            curr->dirp = NULL;

            int is_root = (curr->depth == 0);
            if (!is_root || delete_root_dir) {
                if (dry_run) {
                    stats_out->dirs_deleted++;
                } else if (rmdir_with_force(curr->path, force) == 0) {
                    stats_out->dirs_deleted++;
                } else {
                    if (errno == ENOTEMPTY || errno == EEXIST) {
                        stats_out->skipped++;
                    } else {
                        stats_out->failed++;
                    }
                }
            }

            free(curr->path);
            curr->path = NULL;
            stack_ptr--;
            continue;
        }

        /* Skip "." and ".." */
        if (entry->d_name[0] == '.' && (entry->d_name[1] == '\0' || (entry->d_name[1] == '.' && entry->d_name[2] == '\0'))) {
            continue;
        }

        /* Build child path */
        size_t name_len = strlen(entry->d_name);
        size_t need = curr->path_len + 1 + name_len + 1;
        char *full_path = (char *)malloc(need);
        if (!full_path) {
            stats_out->failed++;
            continue;
        }
        memcpy(full_path, curr->path, curr->path_len);
        full_path[curr->path_len] = '/';
        memcpy(full_path + curr->path_len + 1, entry->d_name, name_len);
        full_path[curr->path_len + 1 + name_len] = '\0';

        /* Classify entry (DT_UNKNOWN handled via lstat fallback) */
        int is_dir = 0;
        int is_lnk = 0;
        off_t fsize = 0;

        if (entry->d_type == DT_DIR) {
            is_dir = 1;
        } else if (entry->d_type == DT_LNK) {
            is_lnk = 1;
        } else if (entry->d_type == DT_REG) {
            struct stat ent_st;
            if (lstat(full_path, &ent_st) == 0) {
                fsize = ent_st.st_size;
            }
        } else if (entry->d_type == DT_UNKNOWN) {
            struct stat ent_st;
            if (lstat(full_path, &ent_st) == 0) {
                if (S_ISDIR(ent_st.st_mode)) {
                    is_dir = 1;
                } else if (S_ISLNK(ent_st.st_mode)) {
                    is_lnk = 1;
                } else if (S_ISREG(ent_st.st_mode)) {
                    fsize = ent_st.st_size;
                }
            } else {
                stats_out->failed++;
                free(full_path);
                continue;
            }
        }

        if (is_dir) {
            /* Check max depth */
            if (max_depth > 0 && (curr->depth + 1) > max_depth) {
                stats_out->skipped++;
                free(full_path);
                continue;
            }

            /* Check filesystem boundary before descending */
            if (one_file_system) {
                struct stat d_st;
                if (lstat(full_path, &d_st) == 0 && d_st.st_dev != base_dev) {
                    stats_out->skipped++;
                    free(full_path);
                    continue;
                }
            }

            /* Open subdirectory and push onto stack (grow if needed) */
            DIR *sub_dirp = opendir(full_path);
            if (!sub_dirp) {
                stats_out->failed++;
                free(full_path);
                continue;
            }

            if ((size_t)(stack_ptr + 1) >= stack_cap) {
                size_t new_cap = stack_cap * 2;
                StackFrame *grown = (StackFrame *)realloc(stack, sizeof(StackFrame) * new_cap);
                if (!grown) {
                    closedir(sub_dirp);
                    stats_out->failed++;
                    free(full_path);
                    continue;
                }
                stack = grown;
                stack_cap = new_cap;
            }

            stack_ptr++;
            stack[stack_ptr].dirp = sub_dirp;
            stack[stack_ptr].path = full_path;   /* ownership transferred */
            stack[stack_ptr].path_len = strlen(full_path);
            stack[stack_ptr].depth = curr->depth + 1;
            full_path = NULL;
            continue;
        }

        /* Regular file, symlink, device, socket, fifo */
        stats_out->files_discovered++;

        if (dry_run) {
            stats_out->files_deleted++;
            if (is_lnk) stats_out->symlinks_deleted++;
            stats_out->bytes_deleted += fsize;
            free(full_path);
            continue;
        }

        if (unlink_with_force(full_path, force, is_lnk) == 0) {
            stats_out->files_deleted++;
            if (is_lnk) stats_out->symlinks_deleted++;
            stats_out->bytes_deleted += fsize;
        } else {
            stats_out->failed++;
        }
        free(full_path);
    }

    while (stack_ptr >= 0) {
        if (stack[stack_ptr].dirp) {
            closedir(stack[stack_ptr].dirp);
        }
        free(stack[stack_ptr].path);
        stack_ptr--;
    }

    free(stack);
    return 0;
}
