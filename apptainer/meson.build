project(
    'remind-mfa-apptainer',
    # The Python package metadata is the single source of truth for the version.
    version: run_command(
        'sed', '-n', 's/^version = "\\(.*\\)"/\\1/p', meson.current_source_dir() / '../pyproject.toml',
        check: true,
    ).stdout().strip().split('\n')[0],
    meson_version: '>=1.1',
)

fs = import('fs')

apptainer = find_program('apptainer')
rsync = find_program('rsync')

repo_root = meson.current_source_dir() / '..'

## Options
# mrmfa comes from the git submodule at apptainer/mrmfa or -Dmrmfa_path option
mrmfa_src = get_option('mrmfa_path')
if mrmfa_src == ''
    mrmfa_src = meson.current_source_dir() / 'mrmfa'
endif
if not fs.exists(mrmfa_src / 'DESCRIPTION')
    error(
        'no mrmfa sources at ' + mrmfa_src
        + ' -- run `git submodule update --init apptainer/mrmfa` or set -Dmrmfa_path=<checkout>',
    )
endif

# The madrat archives are not part of the repository; they are
# copied in from a cluster run, e.g. via scripts/copy_madrat_archive.py mfa-archive.
if not fs.is_dir(repo_root / 'madrat_output')
    error(
        'no madrat_output/ directory in ' + repo_root
        + ' -- fetch the rev*_mfa.tgz archives first, e.g. with scripts/copy_madrat_archive.py mfa-archive',
    )
endif

# The remind_mfa_data submodule carries the input-data supplements that the
# archives do not contain; without it the model cannot be built.
if not fs.exists(repo_root / 'remind_mfa_data' / 'dimensions')
    error(
        'remind_mfa_data submodule is empty -- run `git submodule update --init remind_mfa_data`',
    )
endif

## Build context
# Copy the repository and data into a staging directory, excluding files that are not needed for the build.
stage_repo = custom_target(
    'stage-remind-mfa',
    output: 'remind-mfa',
    command: [
        rsync, '-a', '--delete',
        '--exclude', '.git',
        '--exclude', '.venv',
        '--exclude', '__pycache__',
        '--exclude', '/dist',
        '--exclude', '/madrat_output',
        '--exclude', '/apptainer/build*',
        '--exclude', '/apptainer/mrmfa',
        '--exclude', '*.sif',
        # broken symlink to a file that is not part of the repository
        '--exclude', '/CLAUDE.md',
        # data/ holds several GB of previous model output; only the plastics
        # validation table is read at runtime
        '--include', '/data/',
        '--include', '/data/plastics/',
        '--include', '/data/plastics/input/',
        '--include', '/data/plastics/input/**',
        '--exclude', '/data/**',
        repo_root + '/', '@OUTPUT@/',
    ],
    console: true,
    build_always_stale: true,
)

stage_mrmfa = custom_target(
    'stage-mrmfa',
    output: 'mrmfa',
    command: [
        rsync, '-a', '--delete',
        '--exclude', '.git',
        '--exclude', '/renv',
        '--exclude', '.Rproj.user',
        mrmfa_src + '/', '@OUTPUT@/',
    ],
    console: true,
    build_always_stale: true,
)

stage_archives = custom_target(
    'stage-madrat-output',
    output: 'madrat_output',
    command: [
        rsync, '-a', '--delete',
        '--include', 'rev*_mfa.tgz',
        '--exclude', '*',
        repo_root + '/madrat_output/', '@OUTPUT@/',
    ],
    console: true,
    build_always_stale: true,
)

## Build image
sif = custom_target(
    'sif',
    input: files('remind-mfa.def'),
    output: 'remind-mfa-' + meson.project_version() + '.sif',
    command: [apptainer, 'build', '--force'] + ['@OUTPUT@', '@INPUT@'],
    depends: [stage_repo, stage_mrmfa, stage_archives],
    depend_files: files('retrieve_mfa.R', 'extract_input_data.py'),
    build_by_default: true,
    console: true,
)

## Tests
test(
    'mrmfa-r',
    apptainer,
    args: [
        'exec', sif,
        'Rscript', '-e',
        'suppressMessages(library(mrmfa)); cat("mrmfa", as.character(packageVersion("mrmfa")), "\n")',
    ],
    timeout: 120,
)

test(
    'python-env',
    apptainer,
    args: [
        'exec', sif,
        '/opt/remind-mfa/.venv/bin/python', '-c',
        'import flodym, remind_mfa; from importlib.metadata import version; print("flodym", version("flodym"))',
    ],
    timeout: 120,
)

test(
    'model-run',
    find_program('test_run.sh'),
    args: [sif, meson.current_build_dir() / 'test-output', get_option('test_model')],
    timeout: 1800,
)
