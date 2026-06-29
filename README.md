# obsidian-steward

A Claude Code plugin with skills for maintaining Obsidian vaults. Run each skill from
your vault's root directory. Some skills work on vault files directly; others use the
[Obsidian CLI](https://help.obsidian.md) to read the live link graph and therefore need
the Obsidian desktop app running with the vault open.

Each skill does one thing well — see [CONTRIBUTING.md](CONTRIBUTING.md) for the design
philosophy.

## Skills

| Skill            | What it does                                                                       | Obsidian running? |
| ---------------- | ---------------------------------------------------------------------------------- | ----------------- |
| `check-links`    | Find broken wikilinks, embeds, markdown links, and cross-vault `obsidian://` links | Yes               |
| `orphaned-files` | Find (and optionally remove) files in a folder that no note references             | Yes               |
| `file-dedupe`    | Collapse byte-identical duplicate files, repointing every backlink first           | Optional          |
| `empty-folders`  | Find and optionally remove empty directories                                       | No                |

## Related

This plugin is complementary to
[obsidian-skills](https://github.com/kepano/obsidian-skills), which focuses on content
creation (writing markdown, bases, canvas files). This plugin focuses on vault
maintenance and hygiene.

## Installation

```bash
/plugin marketplace add jheddings/obsidian-steward
/plugin install tidy@obsidian-steward
```
