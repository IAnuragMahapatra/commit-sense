---
description: stage specific files and make an atomic conventional commit
---
// turbo-all

1. Stage the specified files (replace `<files>` with space-separated paths)
```
git add <files>
```

2. Commit with a conventional message (replace `<message>`)
```
git -c user.name="Anurag Mahapatra" -c user.email="anurag2005om@gmail.com" commit -m "<message>"
```
