# CLI Creator
## Description
Build composable command-line interfaces with argparse.
## Instructions
1. Use argparse with subcommands for complex CLIs
2. Each subcommand is a separate function with clear docstring
3. Always provide --help, --version, --verbose flags
4. Use --dry-run for dangerous operations
5. Return proper exit codes (0=success, 1=error, 2=invalid args)
6. Write to stdout for data, stderr for diagnostics
7. Support --output for file output, --json for machine-readable format