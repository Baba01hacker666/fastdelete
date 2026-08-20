/*
 * Native C directory deletion benchmark using nftw() (depth-first, physical/no-follow).
 */

#define _XOPEN_SOURCE 700
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <ftw.h>
#include <time.h>
#include <errno.h>

static long g_files_deleted = 0;
static long g_dirs_deleted = 0;
static long g_errors = 0;

int nftw_delete_callback(const char *fpath, const struct stat *sb, int tflag, struct FTW *ftwbuf) {
    (void)sb;
    (void)ftwbuf;

    if (tflag == FTW_DP) {
        if (rmdir(fpath) == 0) {
            g_dirs_deleted++;
        } else {
            g_errors++;
        }
    } else {
        if (unlink(fpath) == 0) {
            g_files_deleted++;
        } else {
            g_errors++;
        }
    }
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <target_directory>\n", argv[0]);
        return 1;
    }

    const char *target = argv[1];

    struct timespec start, end;
    clock_gettime(CLOCK_MONOTONIC, &start);

    // FTW_DEPTH: post-order (contents before dir), FTW_PHYS: do not follow symlinks
    if (nftw(target, nftw_delete_callback, 128, FTW_DEPTH | FTW_PHYS) != 0) {
        // Fallback: try removing target itself if nftw failed on root
        rmdir(target);
    }

    clock_gettime(CLOCK_MONOTONIC, &end);
    double elapsed = (end.tv_sec - start.tv_sec) + (end.tv_nsec - start.tv_nsec) / 1e9;
    long total = g_files_deleted + g_dirs_deleted;

    printf("Pure C nftw: deleted %ld files, %ld dirs in %.4f seconds (%.0f items/s) [errors=%ld]\n",
           g_files_deleted, g_dirs_deleted, elapsed, total / (elapsed > 0.0001 ? elapsed : 0.0001), g_errors);

    return (g_errors > 0) ? 1 : 0;
}
