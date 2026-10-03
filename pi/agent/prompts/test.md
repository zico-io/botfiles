---
description: Generate comprehensive unit tests for a component or function
argument-hint: "<file-or-component>"
---
Generate tests for $1.

Requirements:
- Use the project's test framework (bun test)
- Cover happy path, edge cases, error states, and boundary conditions
- Use descriptive test names that explain the scenario
- Follow existing test patterns in the codebase
- Group related tests with describe blocks
- Mock external dependencies appropriately
- Test both success and failure modes

If there are existing tests, extend them rather than replacing. Follow the co-location convention: tests go next to the source file as `<name>.test.tsx`.
