Build the specified primate image (or all images if none specified).

Run from the `primates/` directory using the Makefile. If the user specifies an image name, run `make <name>.build`. Otherwise, run `make all`.

Before building, check that the Dockerfile exists for the requested target. Report the build output to the user.

$ARGUMENTS
