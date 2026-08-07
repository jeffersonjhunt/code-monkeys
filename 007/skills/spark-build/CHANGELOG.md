# Changelog — spark-build

## [1.0] - 2026-08-07

- Tests are hermetic: drive the script with a fixture cluster.env via $SPARK_CLUSTER_ENV instead of the maintainer's gitignored local config. Fixes five stale assertions (cuda-* image names, SSH_USER).
