---
description: stage all changes and commit with a conventional commit message
---
// turbo-all

1. Stage specific files or all changes
```
git add -A
```

2. Commit with a conventional commit message
```
git -c user.name="Anurag Mahapatra" -c user.email="anurag2005om@gmail.com" commit -m "<message>"
```

3. For atomic commits (specific files only), stage selectively before step 2
```
git add <files>
```
