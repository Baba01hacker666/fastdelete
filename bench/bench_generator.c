/*
 * High-performance multithreaded directory tree generator in C.
 * Generates hundreds of thousands of files, deep directories, and unusual filenames.
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <fcntl.h>
#include <pthread.h>
#include <time.h>
#include <errno.h>

#define DEFAULT_TOTAL_FILES 50000
#define DIRS_PER_THREAD 25
#define NUM_THREADS 8

typedef struct {
    char base_path[2048];
    int thread_id;
    int files_per_thread;
    long created_files;
    long created_dirs;
} ThreadData;

// Sample unusual names (Unicode, emojis, spaces, tabs, dashes, quotes, etc.)
static const char *unusual_names[] = {
    "normal_%d.txt",
    "file with spaces_%d.dat",
    "file\twith\ttabs_%d.log",
    "-leading-dash_%d.tmp",
    "--double-dash_%d.bin",
    ".hidden_dotfile_%d",
    "unicode_café_résumé_%d.txt",
    "emoji_🚀_🔥_🎉_%d.json",
    "cjk_中文_日本語_%d.dat",
    "quotes_\"test\"_'val'_%d.cfg",
    "symbols_!@#$^&()_+_%d.out",
    "long_name_padding_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa_%d.txt"
};
static const int num_unusual = sizeof(unusual_names) / sizeof(unusual_names[0]);

static void create_dummy_file(const char *filepath, int size) {
    int fd = open(filepath, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd >= 0) {
        if (size > 0) {
            char buf[64] = "benchmark test payload data 1234567890\n";
            ssize_t written = write(fd, buf, (size_t)(size < 64 ? size : 64));
            (void)written;
        }
        close(fd);
    }
}

static void *worker_generate(void *arg) {
    ThreadData *data = (ThreadData *)arg;
    char dir_path[4096];
    char sub_path[4096];
    char file_path[4096];

    int files_per_dir = data->files_per_thread / DIRS_PER_THREAD;
    if (files_per_dir < 1) files_per_dir = 1;

    for (int d = 0; d < DIRS_PER_THREAD; d++) {
        snprintf(dir_path, sizeof(dir_path), "%s/t%d_dir_%d", data->base_path, data->thread_id, d);
        if (mkdir(dir_path, 0755) == 0) {
            data->created_dirs++;
        }

        // Nested sub-directory
        snprintf(sub_path, sizeof(sub_path), "%s/sub_%d", dir_path, d);
        if (mkdir(sub_path, 0755) == 0) {
            data->created_dirs++;
        }

        for (int f = 0; f < files_per_dir; f++) {
            const char *pattern = unusual_names[(d * files_per_dir + f) % num_unusual];
            char fname[1024];
            snprintf(fname, sizeof(fname), pattern, f);

            const char *target_dir = (f % 2 == 0) ? dir_path : sub_path;
            snprintf(file_path, sizeof(file_path), "%s/%s", target_dir, fname);

            create_dummy_file(file_path, (f % 5) * 16);
            data->created_files++;

            // Create symlinks occasionally
            if (f % 30 == 0) {
                char link_path[4096];
                snprintf(link_path, sizeof(link_path), "%s/symlink_to_%d.lnk", target_dir, f);
                int r = symlink(file_path, link_path);
                (void)r;
                data->created_files++;
            }
            if (f % 60 == 0) {
                char broken_link[4096];
                snprintf(broken_link, sizeof(broken_link), "%s/broken_link_%d.lnk", target_dir, f);
                int r = symlink("/non/existent/path/for/benchmark", broken_link);
                (void)r;
                data->created_files++;
            }
        }
    }

    return NULL;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <target_directory> [total_files]\n", argv[0]);
        return 1;
    }

    const char *target_dir = argv[1];
    int total_files = (argc >= 3) ? atoi(argv[2]) : DEFAULT_TOTAL_FILES;
    if (total_files <= 0) total_files = DEFAULT_TOTAL_FILES;

    mkdir(target_dir, 0755);

    pthread_t threads[NUM_THREADS];
    ThreadData data[NUM_THREADS];
    int files_per_thread = total_files / NUM_THREADS;

    struct timespec start, end;
    clock_gettime(CLOCK_MONOTONIC, &start);

    for (int i = 0; i < NUM_THREADS; i++) {
        strncpy(data[i].base_path, target_dir, sizeof(data[i].base_path) - 1);
        data[i].base_path[sizeof(data[i].base_path) - 1] = '\0';
        data[i].thread_id = i;
        data[i].files_per_thread = files_per_thread;
        data[i].created_files = 0;
        data[i].created_dirs = 0;
        pthread_create(&threads[i], NULL, worker_generate, &data[i]);
    }

    long grand_files = 0;
    long grand_dirs = 1; // root

    for (int i = 0; i < NUM_THREADS; i++) {
        pthread_join(threads[i], NULL);
        grand_files += data[i].created_files;
        grand_dirs += data[i].created_dirs;
    }

    clock_gettime(CLOCK_MONOTONIC, &end);
    double elapsed = (end.tv_sec - start.tv_sec) + (end.tv_nsec - start.tv_nsec) / 1e9;

    printf("  [Generator] Created %ld files, %ld dirs in %.3fs (%.0f items/s) at %s\n",
           grand_files, grand_dirs, elapsed, (grand_files + grand_dirs) / (elapsed > 0.001 ? elapsed : 0.001), target_dir);

    return 0;
}
