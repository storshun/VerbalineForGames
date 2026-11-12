# Developing the studio

## What it is

A Python package with no web framework: a command line (`cli.py`) that does every step, a small HTTP server
(`server.py`) that serves one HTML page and runs the command line as background jobs, and model adapters
(`models.py`) that each run in whichever Python environment their model needs. A project is reached only through
`project.py`. The page is one self-contained HTML file with no build step.

The design rules that keep it handable to other teams:

- **One project, many games.** Nothing in the package knows a game. A need a game has becomes a setting or a hook,
  documented in the project API.
- **The command line is the engine.** The page never does generation itself; it queues commands. Anything on the
  page can be done, scripted and tested from a terminal.
- **Files are the state.** The studio files are TOML people edit (comments kept), and the work folder is plain WAV and
  JSON. There is no database, so takes from anywhere can be dropped in.
- **Checks without a GPU.** The tests run every rule (jobs, refusals, ordering, parts, joining, Apply, the project
  hooks) on a temporary project with stand-in audio, in seconds, with no models.

## Expected outcome

A contributor can change a step, run the tests, and know the page, the command line and the project API still agree.

## Where the details are

Detailed instruction and information on each module, the job flow, the tests, and how to change the project API or
the page can be found in docs/details/development-details.md.
