#!/bin/bash

if [ $# -ne 3 ]; then
    echo "Usage: ./renderer.sh <user> <password> <feedstock>"
    exit
fi


GH_USER=$1
GH_CRED=$2
FEEDSTOCK=$3
SMITHY_VERSION=$(conda smithy --version | tail -1)
CURHEAD=$GH_USER:master

generate_post_data()
{
  cat <<EOF
{
  "title": "Ticked version, rerendered if needed. (Double-check reqs!)",
  "head": "$CURHEAD",
  "base": "master"
}
EOF
}

echo Starting $FEEDSTOCK...
git clone https://github.com/$GH_USER/$FEEDSTOCK.git
cd $FEEDSTOCK
conda smithy rerender
COMMITMSG="MNT: Re-rendered with conda-smithy $SMITHY_VERSION"
git commit -m "$COMMITMSG"
git push
cd ..
rm -rf $FEEDSTOCK
curl -X POST \
  -H 'Content-Type: application/json' \
  -d "$(generate_post_data)"\
  --user $GH_USER:$GH_CRED \
  https://api.github.com/repos/conda-forge/$FEEDSTOCK/pulls
echo '---------'