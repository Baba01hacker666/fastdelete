/*
 * High-performance C deletion engine for fastdelete.
 * Uses direct POSIX streaming readdir(), unlink(), rmdir(), and iterative stack traversal.
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
#include <pthread.h>

#define MAX_PATH_LEN 4096
#define MAX_DEPTH 1024

typedef struct {
    uint64_t files_discovered;
    uint64_t files_deleted;
    uint64_t dirs_deleted;
    uint64_t bytes_deleted;
    uint64_t skipped;
    uint64_t failed;
} CDeleteStats;

typedef struct {
    DIR *dirp;
    char path[MAX_PATH_LEN];
    int depth;
    dev_t dev;
} StackFrame;

// Force permissions on read-only file/dir
static int try_force_chmod(const char *path, mode_t extra_mode) {
    struct stat st;
    if (lstat(path, &st) == 0) {
        mode_t new_mode = st.st_mode | S_IWUSR | extra_mode;
        return chmod(path, new_mode);
    }
    return -1;
}

// Single-threaded high-performance C tree deleter
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

    // If target is not a directory or is a symlink
    if (!S_ISDIR(root_st.st_mode) || S_ISLNK(root_st.st_mode)) {
        stats_out->files_discovered++;
        if (dry_run) {
            stats_out->files_deleted++;
            stats_out->bytes_deleted += S_ISREG(root_st.st_mode) ? root_st.st_size : 0;
            return 0;
        }

        if (unlink(target_path) == 0 || errno == ENOENT) {
            stats_out->files_deleted++;
            stats_out->bytes_deleted += S_ISREG(root_st.st_mode) ? root_st.st_size : 0;
            return 0;
        } else if (force && try_force_chmod(target_path, 0) == 0 && unlink(target_path) == 0) {
            stats_out->files_deleted++;
            stats_out->bytes_deleted += S_ISREG(root_st.st_mode) ? root_st.st_size : 0;
            return 0;
        } else {
            stats_out->failed++;
            return -1;
        }
    }

    // Target is a directory -> iterative post-order traversal stack
    StackFrame *stack = (StackFrame *)malloc(sizeof(StackFrame) * MAX_DEPTH);
    if (!stack) return -2;

    int stack_ptr = 0;
    DIR *root_dirp = opendir(target_path);
    if (!root_dirp) {
        free(stack);
        stats_out->failed++;
        return -1;
    }

    stack[0].dirp = root_dirp;
    strncpy(stack[0].path, target_path, MAX_PATH_LEN - 1);
    stack[0].path[MAX_PATH_LEN - 1] = '\0';
    stack[0].depth = 0;
    stack[0].dev = base_dev;

    char full_path[MAX_PATH_LEN];

    while (stack_ptr >= 0) {
        if (abort_flag && *abort_flag) {
            break;
        }

        StackFrame *curr = &stack[stack_ptr];
        errno = 0;
        struct dirent *entry = readdir(curr->dirp);

        if (!entry) {
            // End of directory reached: close and remove directory (post-order)
            closedir(curr->dirp);
            curr->dirp = NULL;

            int is_root = (curr->depth == 0);
            if (!is_root || delete_root_dir) {
                if (dry_run) {
                    stats_out->dirs_deleted++;
                } else {
                    if (rmdir(curr->path) == 0 || errno == ENOENT) {
                        stats_out->dirs_deleted++;
                    } else if (force && try_force_chmod(curr->path, S_IXUSR) == 0 && rmdir(curr->path) == 0) {
                        stats_out->dirs_deleted++;
                    } else {
                        if (errno == ENOTEMPTY || errno == EEXIST) {
                            stats_out->skipped++;
                        } else {
                            stats_out->failed++;
                        }
                    }
                }
            }

            stack_ptr--;
            continue;
        }

        // Skip "." and ".."
        if (entry->d_name[0] == '.' && (entry->d_name[1] == '\0' || (entry->d_name[1] == '.' && entry->d_name[2] == '\0'))) {
            continue;
        }

        // Build child path
        size_t parent_len = strlen(curr->path);
        size_t name_len = strlen(entry->d_name);
        if (parent_len + 1 + name_len >= MAX_PATH_LEN) {
            stats_out->failed++;
            continue;
        }

        memcpy(full_path, curr->path, parent_len);
        full_path[parent_len] = '/';
        memcpy(full_path + parent_len + 1, entry->d_name, name_len);
        full_path[parent_len + 1 + name_len] = '\0';

        // Check entry type (DT_UNKNOWN handling fallback)
        int is_dir = 0;
        int is_lnk = 0;
        off_t fsize = 0;

        if (entry->d_type == DT_DIR) {
            is_dir = 1;
        } else if (entry->d_type == DT_LNK) {
            is_lnk = 1;
        } else if (entry->d_type == DT_UNKNOWN) {
            struct stat ent_st;
            if (lstat(full_path, &ent_st) == 0) {
                if (S_ISDIR(ent_st.st_mode) && !S_ISLNK(ent_st.st_mode)) {
                    is_dir = 1;
                } else if (S_ISLNK(ent_st.st_mode)) {
                    is_lnk = 1;
                }
                if (S_ISREG(ent_st.st_mode)) {
                    fsize = ent_st.st_size;
                }
            }
        }

        if (is_dir) {
            // Check max depth
            if (max_depth > 0 && (curr->depth + 1) > max_depth) {
                stats_out->skipped++;
                continue;
            }

            // Check filesystem boundary
            if (one_file_system) {
                struct stat d_st;
                if (lstat(full_path, &d_st) == 0 && d_st.st_dev != base_dev) {
                    stats_out->skipped++;
                    continue;
                }
            }

            // Open subdirectory and push onto stack
            if (stack_ptr + 1 >= MAX_DEPTH) {
                stats_out->failed++;
                continue;
            }

            DIR *sub_dirp = opendir(full_path);
            if (!sub_dirp) {
                stats_out->failed++;
                continue;
            }

            stack_ptr++;
            stack[stack_ptr].dirp = sub_dirp;
            strncpy(stack[stack_ptr].path, full_path, MAX_PATH_LEN - 1);
            stack[stack_ptr].path[MAX_PATH_LEN - 1] = '\0';
            stack[stack_ptr].depth = curr->depth + 1;
            stack[stack_ptr].dev = base_dev;
        } else {
            // Regular file, symlink, device, socket, fifo
            // Note: Directory symlinks are also DT_LNK and are unlinked here without following!
            stats_out->files_discovered++;

            if (dry_run) {
                stats_out->files_deleted++;
                stats_out->bytes_deleted += fsize;
                continue;
            }

            if (unlink(full_path) == 0 || errno == ENOENT) {
                stats_out->files_deleted++;
                stats_out->bytes_deleted += fsize;
            } else if (force && try_force_chmod(full_path, 0) == 0 && unlink(full_path) == 0) {
                stats_out->files_deleted++;
                stats_out->bytes_deleted += fsize;
            } else {
                stats_out->failed++;
            }
        }
    }

    // Clean up any remaining open descriptors if aborted early
    while (stack_ptr >= 0) {
        if (stack[stack_ptr].dirp) {
            closedir(stack[stack_ptr].dirp);
        }
        stack_ptr--;
    }

    free(stack);
    return 0;
}
