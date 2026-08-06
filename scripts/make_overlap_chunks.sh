#!/usr/bin/env bash
#
# make_overlap_chunks.sh
# -----------------------
# Build symlink folders so adjacent runs (chunks) share their boundary flight
# lines, giving Metashape cameras in common to align the chunks on before
# merging them (avoids the out-of-memory that a tie-point merge causes on large
# projects).
#
# Because src/metashape_workflow_functions_lefolab.py sets each camera's label
# to its photo *path*, both runs on either side of a seam must reference the
# seam photos through the SAME directory (so the labels match), and each run
# must add each seam photo only once (so Metashape doesn't align an identical
# image twice).
#
# Supports any number of runs laid out in a chain (run A - run B - run C - ...).
# For each SEAM (a pair of adjacent runs) it creates:
#   overlap_<A>_<B>/from_<A>, overlap_<A>_<B>/from_<B>   <- listed by BOTH A and B
# For each run it creates:
#   <name>_main/   <- that run's missions MINUS every seam line it contributes
#
# A run in two seams (e.g. the middle of a chain) excludes both seams' lines
# from its _main and lists both overlap folders in its images_path. The final
# images_path for every config is printed at the end.
#
# Usage:
#   ./scripts/make_overlap_chunks.sh            # build the folders
#   ./scripts/make_overlap_chunks.sh --dry-run  # print what it would do only
#
# Requires GNU coreutils (cp -as) -- standard on Linux. Run on the machine that
# has the NFS share mounted at the same absolute path Metashape will use.

set -euo pipefail

# ============================ EDIT THIS BLOCK ============================
ROOT=/path/to/your/project

PREFIX=P          # filename prefix, e.g. "P" in P0008109.jpg
PAD=7             # number of digits after the prefix (P0008109 -> 7)

# --- Runs: choose any name you like -> the missions that make up that run.
#     Mission folders are names directly under $ROOT. Add as many runs as needed.
declare -A RUN_MISSIONS=(
  [run1a]="mission1 mission2"
  [run2a]="mission3 mission4"
)

# --- Seams: one entry per pair of ADJACENT runs that will be merged together.
#     Format (fields separated by "|"):
#        "RUNA RUNB | RUNA lines | RUNB lines"
#     where each "lines" field is one or more "mission START END" triples
#     (inclusive numeric range), multiple triples separated by ";".
#     Example second seam below uses placeholder ranges -- edit to your data.
SEAMS=(
  "run1a run2a | mission2 100 200 | mission3 201 300"
)
# =========================================================================

DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

run() { if [[ $DRY -eq 1 ]]; then echo "  [dry-run] $*"; else eval "$@"; fi; }
die() { echo "ERROR: $*" >&2; exit 1; }

[[ -d "$ROOT" ]] || die "ROOT does not exist: $ROOT"
command -v cp >/dev/null || die "cp not found"
cp --help 2>/dev/null | grep -q -- '-s,' \
  || die "your 'cp' has no -s (symlink) option -- GNU coreutils required"

echo "ROOT = $ROOT   (dry-run=$DRY)"

# Normalise a "lines" field into one "mission START END" per line.
expand_triples() {
  local spec=$1 t src start end parts
  IFS=';' read -ra parts <<<"$spec"
  for t in "${parts[@]}"; do
    read -r src start end <<<"$t"       # default IFS trims surrounding spaces
    [[ -n "${src:-}" ]] && printf '%s %s %s\n' "$src" "$start" "$end"
  done
}

# Symlink one side of a seam into its overlap subfolder.
# Photos may be nested (mission1/log_0270_Geotagged/P5 (80mm)/...), so each
# source folder is indexed recursively once into a stem -> path map.
link_side() {   # label  target_dir  spec
  local label=$1 target=$2 spec=$3
  run "mkdir -p \"$target\""
  local src start end n stem srcfile base count=0 missing=0
  local -A indexed=() stem2path=()
  local f b s
  while read -r src start end; do
    [[ -z "${src:-}" ]] && continue
    [[ -d "$ROOT/$src" ]] || die "seam source folder missing: $ROOT/$src"
    if [[ -z "${indexed[$src]:-}" ]]; then
      while IFS= read -r -d '' f; do
        b=$(basename "$f"); s=${b%.*}
        stem2path["$src/$s"]=$f
      done < <(find "$ROOT/$src" -type f \
                 \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.tif' -o -iname '*.tiff' \) \
                 -print0 2>/dev/null)
      indexed[$src]=1
    fi
    for ((n = 10#$start; n <= 10#$end; n++)); do
      stem=$(printf "%s%0${PAD}d" "$PREFIX" "$n")
      srcfile=${stem2path["$src/$stem"]:-}
      if [[ -n "$srcfile" ]]; then
        base=$(basename "$srcfile")
        run "ln -sf \"$srcfile\" \"$target/$base\""
        count=$((count + 1))
      else
        missing=$((missing + 1))
      fi
    done
  done < <(expand_triples "$spec")
  echo "  $label: linked $count, $missing not found on disk"
}

declare -A RUN_SEAM_RANGES   # run name -> its contributed "mission START END" lines
declare -A RUN_OVERLAPS      # run name -> space-separated overlap dir names

echo "[1/3] building overlap folders ..."
for seam in "${SEAMS[@]}"; do
  IFS='|' read -r pair aspec bspec <<<"$seam"
  read -r A B <<<"$pair"
  [[ -n "${A:-}" && -n "${B:-}" ]] || die "malformed seam (need two runs): $seam"
  [[ -n "${RUN_MISSIONS[$A]:-}" ]] || die "seam references unknown run: $A"
  [[ -n "${RUN_MISSIONS[$B]:-}" ]] || die "seam references unknown run: $B"
  ov="overlap_${A}_${B}"
  link_side "$ov/from_$A" "$ROOT/$ov/from_$A" "$aspec"
  link_side "$ov/from_$B" "$ROOT/$ov/from_$B" "$bspec"
  RUN_SEAM_RANGES[$A]+="$(expand_triples "$aspec")"$'\n'
  RUN_SEAM_RANGES[$B]+="$(expand_triples "$bspec")"$'\n'
  RUN_OVERLAPS[$A]+="$ov "
  RUN_OVERLAPS[$B]+="$ov "
done

# Build one run's _main folder: its missions, minus every seam line it contributes.
build_main() {   # run_name
  local name=$1
  local target="$ROOT/${name}_main"
  local missions=${RUN_MISSIONS[$name]}
  run "rm -rf \"$target\""            # idempotent: only removes this generated tree
  run "mkdir -p \"$target\""
  local paths=() m
  for m in $missions; do
    [[ -d "$ROOT/$m" ]] || die "mission folder missing: $ROOT/$m"
    paths+=("$ROOT/$m")
  done
  run "cp -as ${paths[*]} \"$target/\""
  local src start end n stem
  while read -r src start end; do
    [[ -z "${src:-}" ]] && continue
    for ((n = 10#$start; n <= 10#$end; n++)); do
      stem=$(printf "%s%0${PAD}d" "$PREFIX" "$n")
      run "find \"$target\" -iname \"$stem.*\" -delete"
    done
  done <<<"${RUN_SEAM_RANGES[$name]:-}"
  echo "  ${name}_main: from [$missions] minus own seam lines"
}

# Bash returns associative-array keys in hash order, so sort them for stable logs.
mapfile -t RUN_NAMES < <(printf '%s\n' "${!RUN_MISSIONS[@]}" | sort -V)

echo "[2/3] building per-run main folders ..."
for name in "${RUN_NAMES[@]}"; do build_main "$name"; done

echo "[3/3] images_path for each config:"
for name in "${RUN_NAMES[@]}"; do
  line="[\"$ROOT/${name}_main\""
  for ov in ${RUN_OVERLAPS[$name]:-}; do line+=", \"$ROOT/$ov\""; done
  line+="]"
  printf '  %-8s images_path: %s\n' "$name:" "$line"
done

echo
echo "Each config's images_path is printed above. Both runs on a seam list the"
echo "same overlap_* folder, so the seam photos get identical labels in both"
echo "chunks -- which is what camera-based Align Chunks matches the chunks on."
echo
echo "Run each config with load_project + new_chunk: True so every run lands as"
echo "a chunk of the same project, then:"
echo "  python scripts/run_task.py --project <project>.psx \\"
echo "      --task align_chunks --task merge_chunks --task deduplicate_cameras"
echo
echo "The merge keeps both copies of each seam photo (one per source chunk);"
echo "deduplicate_cameras disables the extras so each photo is used once."
