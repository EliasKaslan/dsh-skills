#!/usr/bin/env bash
# 一次性迁移：把 /mnt/share/x00886548 下的内容并回个人根（.188），并在旧路径留软链
set -e
R=/home/x00886548
M=/mnt/share/x00886548

echo "== step0 precheck"
readlink -f $R
ls -d $R/env $R/work >/dev/null || { echo "skeleton missing"; exit 1; }

echo "== step1 move conda (>1.2G, 跨盘复制)"
if [ -d $M/miniconda3 ] && [ ! -L $M/miniconda3 ]; then
  mv $M/miniconda3 $R/env/conda3
  ln -s $R/env/conda3 $M/miniconda3
  echo "moved conda"
else echo "skip conda"; fi

echo "== step2 move cann (>15G, 跨盘复制)"
if [ -d $M/cann ] && [ ! -L $M/cann ]; then
  for x in $M/cann/*; do mv "$x" $R/env/cann/; done
  rmdir $M/cann
  ln -s $R/env/cann $M/cann
  echo "moved cann"
else echo "skip cann"; fi

echo "== step3 move workspace"
if [ -d $M/workspace ] && [ ! -L $M/workspace ]; then
  for x in $M/workspace/*; do mv "$x" $R/work/; done
  rmdir $M/workspace
  ln -s $R/work $M/workspace
  echo "moved workspace"
else echo "skip workspace"; fi

echo "== step4 setup_conda.sh -> env/"
if [ -f $R/work/setup_conda.sh ]; then
  mv $R/work/setup_conda.sh $R/env/setup_conda.sh
  ln -s ../env/setup_conda.sh $R/work/setup_conda.sh
  echo "moved setup_conda.sh"
fi

echo "== step5 misc"
if [ -d $M/env_pkgs ]; then for x in $M/env_pkgs/*; do mv "$x" $R/env/pkgs/; done; rmdir $M/env_pkgs; echo "moved env_pkgs"; fi
if [ -d $M/pip-cache ]; then rmdir $M/pip-cache && echo "rmdir pip-cache"; fi
if [ -d $M/tmp ]; then mv $M/tmp $R/tmp/legacy-mnt-share && echo "moved tmp"; fi

echo "== step6 leftover at $M"
ls -la $M

echo "== step7 condarc envs_dirs/pkgs_dirs"
python3 - "$R/env/conda3/.condarc" <<'PY'
import io, re, sys
p = sys.argv[1]
s = io.open(p, encoding='utf-8').read()
s = re.sub(r"(?ms)^envs_dirs:\n(?:[ \t]+-.*\n)+",
           "envs_dirs:\n  - /home/x00886548/env/conda_envs\n  - /mnt/share/vllm/conda_envs\n  - /root/miniconda3/envs\n", s)
s = re.sub(r"(?ms)^pkgs_dirs:\n(?:[ \t]+-.*\n)+",
           "pkgs_dirs:\n  - /home/x00886548/env/pkgs/conda\n  - /mnt/share/vllm/conda_pkgs\n  - /root/miniconda3/pkgs\n", s)
io.open(p, 'w', encoding='utf-8', newline='\n').write(s)
print("condarc rewritten")
PY
sed -n '/envs_dirs/,$p' $R/env/conda3/.condarc

echo "== step8 verify"
readlink -f $R
ls -la $R
$M/miniconda3/bin/conda --version
$M/miniconda3/bin/conda info 2>/dev/null | grep -E "base environment|python version"
source $M/miniconda3/etc/profile.d/conda.sh && conda env list
echo "== step9 df"
df -h $R / /home/vllm | tail -4
