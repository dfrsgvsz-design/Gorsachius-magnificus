# Contributing Guidelines

Thank you for your interest in contributing to the Gorsachius magnificus project.

## Getting Started

1. Read [`DEVELOPMENT.md`](DEVELOPMENT.md) to set up your local environment.
2. Review [`ARCHITECTURE.md`](ARCHITECTURE.md) to understand the project structure.

## Workflow

1. Create a feature branch from the latest `main`.
2. Make your changes in small, focused commits.
3. Ensure backend syntax checks pass: `python -m compileall .`
4. Ensure frontend builds succeed: `npm run build`
5. Run backend tests: `pytest tests/`
6. Submit a pull request with a clear description of changes.

## Code Style

- **Python**: Follow PEP 8. Use type hints where practical.
- **TypeScript/React**: Follow the existing ESLint and Prettier configuration in each frontend project.
- **Commits**: Use concise, descriptive commit messages.

## Reporting Issues

Open an issue with:
- A clear title and description
- Steps to reproduce (if applicable)
- Expected vs. actual behavior
- Environment details (OS, Python version, Node version)

## Project-Specific Notes

- **acoustic_platform** and **species_monitoring_platform** share backend modules under `shared/backend/`. Changes to shared code affect both platforms.
- **project_sdm_stoten** is a research project with its own analysis pipeline; coordinate with the research lead before modifying analysis scripts or manuscript materials.
