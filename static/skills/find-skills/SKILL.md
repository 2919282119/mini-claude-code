---
name: find-skills
description: Helps users discover and install agent skills when they ask questions like "how do I do X", "find a skill for X", "is there a skill that can...", or express interest in extending capabilities. This skill should be used when the user is looking for functionality that might exist as an installable skill.
---

# Find Skills

This skill helps you discover and install skills from the open agent skills ecosystem.

## Important: miniCC Skill Installation

**All skills used by miniCC must be installed into the miniCC global skills directory:**

```text
~/.miniCC/skills/
```

Each installed skill must have its own directory:

```text
~/.miniCC/skills/<skill-name>/SKILL.md
```

For example:

```text
~/.miniCC/skills/brainstorming/SKILL.md
```

**Do not use `npx skills add -g` as the final installation method.**

The `-g` option of the Skills CLI installs skills into the Skills CLI ecosystem's global location (such as `~/.agents/skills`), which is **not** the miniCC skill directory.

If the Skills CLI is used to download or obtain a skill, the resulting skill files must be copied or installed into:

```text
~/.miniCC/skills/<skill-name>/
```

Do not delete or modify an existing skill outside `~/.miniCC/skills` unless the user explicitly asks you to do so.

## When to Use This Skill

Use this skill when the user:

- Asks "how do I do X" where X might be a common task with an existing skill
- Says "find a skill for X" or "is there a skill for X"
- Asks "can you do X" where X is a specialized capability
- Expresses interest in extending agent capabilities
- Wants to search for tools, templates, or workflows
- Mentions they wish they had help with a specific domain (design, testing, deployment, etc.)

## What is the Skills CLI?

The Skills CLI (`npx skills`) is a package manager for the open agent skills ecosystem. Skills are modular packages that extend agent capabilities with specialized knowledge, workflows, and tools.

**Key commands:**

- `npx skills find [query]` - Search for skills interactively or by keyword
- `npx skills add <package>` - Download/install a skill from GitHub or other sources
- `npx skills check` - Check for skill updates
- `npx skills update` - Update installed skills

**Browse skills at:** https://skills.sh/

### Important

The Skills CLI's global installation directory is **not** the miniCC skill directory.

Therefore:

```bash
npx skills add <package> -g -y
```

must **not** be treated as the final installation step for miniCC.

If this command is used to obtain the skill, locate the downloaded skill and copy its complete skill directory into:

```text
~/.miniCC/skills/<skill-name>/
```

Make sure `SKILL.md` exists in the final directory.

## How to Help Users Find Skills

### Step 1: Understand What They Need

When a user asks for help with something, identify:

1. The domain (e.g., React, testing, design, deployment)
2. The specific task (e.g., writing tests, creating animations, reviewing PRs)
3. Whether this is a common enough task that a skill likely exists

### Step 2: Check the Leaderboard First

Before running a CLI search, check the skills.sh leaderboard to see if a well-known skill already exists for the domain.

The leaderboard ranks skills by total installs, surfacing popular and battle-tested options.

For example, top skills for web development may include:

- `vercel-labs/agent-skills` — React, Next.js, web design
- `anthropics/skills` — Frontend design, document processing

### Step 3: Search for Skills

If the leaderboard doesn't cover the user's need, run:

```bash
npx skills find [query]
```

For example:

- User asks "how do I make my React app faster?" → `npx skills find react performance`
- User asks "can you help me with PR reviews?" → `npx skills find pr review`
- User asks "I need to create a changelog" → `npx skills find changelog`

### Step 4: Verify Quality Before Recommending

**Do not recommend a skill based solely on search results.**

Always verify:

1. **Install count** — Prefer skills with 1K+ installs. Be cautious with anything under 100.
2. **Source reputation** — Official sources such as `vercel-labs`, `anthropics`, or `microsoft` are generally more trustworthy than unknown authors.
3. **GitHub stars** — Check the source repository. A skill from a repo with very few stars should be treated with skepticism.

### Step 5: Present Options to the User

When you find relevant skills, present:

1. The skill name and what it does
2. The install count and source
3. The installation source/package
4. A link to learn more at skills.sh

Example:

```text
I found a skill that might help!

The "react-best-practices" skill provides React and Next.js
performance optimization guidelines from Vercel Engineering.

Source:
vercel-labs/agent-skills@react-best-practices

Learn more:
https://skills.sh/vercel-labs/agent-skills/react-best-practices
```

### Step 6: Install the Skill

If the user wants to install the skill:

1. Obtain the skill from its source.
2. Install/copy the **complete skill directory** into:

```text
~/.miniCC/skills/<skill-name>/
```

3. Verify that:

```text
~/.miniCC/skills/<skill-name>/SKILL.md
```

exists.
4. Do not leave the skill only in `~/.agents/skills`.
5. Do not delete an existing copy outside `~/.miniCC/skills` unless explicitly requested by the user.

If the Skills CLI is used to obtain the skill, it may be used as a download/source mechanism, for example:

```bash
npx skills add <owner/repo@skill> -g -y
```

However, **this is not the final installation location for miniCC**.

After the command completes, locate the downloaded skill directory and copy it to:

```text
~/.miniCC/skills/<skill-name>/
```

For example:

```text
~/.agents/skills/brainstorming/
        ↓
~/.miniCC/skills/brainstorming/
```

The destination is the authoritative miniCC installation.

**Never delete the source copy automatically.** Only remove temporary downloaded files when it is clear that they were created solely for the current installation and removing them will not affect another agent or application.

### Common Skill Categories

When searching, consider these common categories:

| Category | Example Queries |
| --- | --- |
| Web Development | react, nextjs, typescript, css, tailwind |
| Testing | testing, jest, playwright, e2e |
| DevOps | deploy, docker, kubernetes, ci-cd |
| Documentation | docs, readme, changelog, api-docs |
| Code Quality | review, lint, refactor, best-practices |
| Design | ui, ux, design-system, accessibility |
| Productivity | workflow, automation, git |

## Tips for Effective Searches

1. **Use specific keywords:** "react testing" is better than just "testing".
2. **Try alternative terms:** If "deploy" doesn't work, try "deployment" or "ci-cd".
3. **Check popular sources:** Many skills come from `vercel-labs/agent-skills` or `ComposioHQ/awesome-claude-skills`.

## When No Skills Are Found

If no relevant skill exists:

1. Acknowledge that no existing skill was found.
2. Offer to help with the task directly using general capabilities.
3. Suggest that the user could create their own skill.

For example:

```text
I searched for skills related to "xyz" but didn't find any matches.

I can still help you with this task directly.

If this is something you do often, you could create your own skill.
```