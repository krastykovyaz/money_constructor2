#!/bin/bash
git filter-branch --env-filter '
if [ "$GIT_AUTHOR_EMAIL" = "dmitrii.koriakov@uni.lu" ]; then
    export GIT_AUTHOR_NAME="Iaroslav NEVEROV"
    export GIT_AUTHOR_EMAIL="beeguy74@gmail.com"
fi
if [ "$GIT_COMMITTER_EMAIL" = "dmitrii.koriakov@uni.lu" ]; then
    export GIT_COMMITTER_NAME="Iaroslav NEVEROV"
    export GIT_COMMITTER_EMAIL="beeguy74@gmail.com"
fi
' -- --all