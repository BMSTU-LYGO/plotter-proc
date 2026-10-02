# Multi-agent model routing

The primary agent is the orchestrator.

Use subagents aggressively when a task can be safely delegated.

## Luna

Delegate to `luna_worker` for simple, bounded work:

- repository exploration
- searching files
- locating symbols
- reading and summarizing code
- repetitive mechanical edits
- formatting
- renaming
- boilerplate
- simple documentation
- straightforward tests
- simple configuration changes

Do not perform these tasks with the primary model when Luna can
reliably handle them.

## Terra

Delegate to `terra_worker` for normal implementation work:

- implementing well-defined features
- refactoring
- normal bug fixes
- unit and integration tests
- routine debugging
- changes involving multiple related files

Prefer Terra over the primary model whenever the task is
well-defined and does not require difficult reasoning.

## Primary Sol agent

Keep work on the primary agent for:

- architecture
- task decomposition
- ambiguous requirements
- difficult debugging
- complex reasoning
- security-sensitive decisions
- cross-system design
- resolving conflicts between subagent results
- final review

## Escalation

Use this hierarchy:

Luna -> Terra -> Sol

If Luna determines that its task is too difficult, escalate it to Terra.
If Terra determines that the problem requires architectural or difficult
reasoning, return it to Sol.

## Final verification

The primary agent is responsible for reviewing important changes made
by subagents before considering the overall task complete.

Parallelize independent subagent tasks when useful.
