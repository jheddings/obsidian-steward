# justfile for obsidian-skills

# auto-format all files
tidy:
    npx prettier --write .

# run all checks
check: style validate

# check style
style:
    npx prettier --check .

# validate all skills against the Agent Skills spec
validate:
    for dir in skills/*/; do npx skills-ref validate "$dir"; done
