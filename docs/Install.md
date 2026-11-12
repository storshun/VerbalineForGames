# Installing and configuring

## What it is

The studio is a small Python package plus the models it drives. The package itself needs little (numpy, scipy,
soundfile, pyloudnorm, tomlkit); the models need PyTorch with CUDA and, because they pin clashing library versions,
usually a Python environment each. The studio knows which environment each job needs and re-runs itself there.

Settings come in three layers: the studio's defaults, the machine's config (where the models and environments are),
and each project's `verbaline.toml` (everything about that game). A project never names a path on someone's machine;
a machine's config never names a game.

The page can run by hand (`verbaline serve`) or as a background service that's always up, one per project, each on
its own port.

## Expected outcome

On a machine with an NVIDIA GPU and its driver, a new user goes from a clone to generating takes for the example
project in about half an hour, most of it downloads. Engines that aren't installed simply don't appear, and the page
says what an engine is missing.

## Where the details are

Detailed instruction and information on installing the package, each model and environment, the GPU, and the
service can be found in docs/details/install-details.md.
Detailed instruction and information on every setting, its default and its effect can be found in
docs/details/configuration-details.md.
