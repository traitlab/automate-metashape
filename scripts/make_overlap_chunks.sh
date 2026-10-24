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
# Incremental: each generated folder's inputs (seam ranges, or a run's missions
# plus its seam ranges) are recorded in $ROOT/.overlap_state/<folder>.sig. A
# folder whose inputs are unchanged since the last build is skipped, so adding
# a run and a seam only builds the new folders and rebuilds the neighbouring
# run's _main.
#
# Usage:
#   ./scripts/make_overlap_chunks.sh              # build new/changed folders
#   ./scripts/make_overlap_chunks.sh --dry-run    # print what it would do only
#   ./scripts/make_overlap_chunks.sh --force      # rebuild every folder

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

run() { if [[ $DRY -eq 1 ]]; then echo "  [dry-run] $*"; else eval "$@"; fi; }
die() { echo "ERROR: $*" >&2; exit 1; }

DRY=0; FORCE=0
for arg in "$@"; do
  case $arg in
    --dry-run)    DRY=1 ;;
    --force)      FORCE=1 ;;
    *) die "unknown option: $arg" ;;
  esac
done

[[ -d "$ROOT" ]] || die "ROOT does not exist: $ROOT"
command -v cp >/dev/null || die "cp not found"
cp --help 2>/dev/null | grep -q -- '-s,' \
  || die "your 'cp' has no -s (symlink) option -- GNU coreutils required"

STATE="$ROOT/.overlap_state"

echo "ROOT = $ROOT   (dry-run=$DRY force=$FORCE)"

# Normalise a "lines" field into one "mission START END" per line.
expand_triples() {
  local spec=$1 t src start end parts
  IFS=';' read -ra parts <<<"$spec"
  for t in "${parts[@]}"; do
    read -r src start end <<<"$t"       # default IFS trims surrounding spaces
    [[ -n "${src:-}" ]] && printf '%s %s %s\n' "$src" "$start" "$end"
  done
}

# Signatures: the inputs a generated folder is built from. A folder is rebuilt
# only when its signature differs from the one saved at its last build.
seam_sig() {   # A B aspec bspec
  printf 'prefix=%s pad=%s\n' "$PREFIX" "$PAD"
  printf 'from_%s:\n' "$1"; expand_triples "$3"
  printf 'from_%s:\n' "$2"; expand_triples "$4"
}
main_sig() {   # run_name
  local missions
  read -ra missions <<<"${RUN_MISSIONS[$1]}"
  printf 'prefix=%s pad=%s\n' "$PREFIX" "$PAD"
  printf 'missions: %s\n' "${missions[*]}"
  printf 'seam lines:\n'
  printf '%s' "${RUN_SEAM_RANGES[$1]:-}" | sed '/^$/d' | sort -V
}
is_current() {   # dir sigfile sig
  [[ $FORCE -eq 0 && -d "$1" && -f "$2" ]] && [[ "$(<"$2")" == "$3" ]]
}
save_sig() {   # sigfile sig
  if [[ $DRY -eq 1 ]]; then echo "  [dry-run] save signature $1"; return; fi
  mkdir -p "$STATE"
  printf '%s\n' "$2" >"$1"
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
        b=${f##*/}; s=${b%.*}
        stem2path["$src/$s"]=$f
      done < <(find "$ROOT/$src" -type f \
                 \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.tif' -o -iname '*.tiff' \) \
                 -print0 2>/dev/null)
      indexed[$src]=1
    fi
    for ((n = 10#$start; n <= 10#$end; n++)); do
      printf -v stem "%s%0${PAD}d" "$PREFIX" "$n"
      srcfile=${stem2path["$src/$stem"]:-}
      if [[ -n "$srcfile" ]]; then
        base=${srcfile##*/}
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
declare -A EXPECTED          # generated folder names the current config defines

echo "[1/3] building overlap folders ..."
for seam in "${SEAMS[@]}"; do
  IFS='|' read -r pair aspec bspec <<<"$seam"
  read -r A B <<<"$pair"
  [[ -n "${A:-}" && -n "${B:-}" ]] || die "malformed seam (need two runs): $seam"
  [[ -n "${RUN_MISSIONS[$A]:-}" ]] || die "seam references unknown run: $A"
  [[ -n "${RUN_MISSIONS[$B]:-}" ]] || die "seam references unknown run: $B"
  ov="overlap_${A}_${B}"
  RUN_SEAM_RANGES[$A]+="$(expand_triples "$aspec")"$'\n'
  RUN_SEAM_RANGES[$B]+="$(expand_triples "$bspec")"$'\n'
  RUN_OVERLAPS[$A]+="$ov "
  RUN_OVERLAPS[$B]+="$ov "
  EXPECTED[$ov]=1

  sig=$(seam_sig "$A" "$B" "$aspec" "$bspec")
  sigfile="$STATE/$ov.sig"
  if is_current "$ROOT/$ov" "$sigfile" "$sig"; then
    echo "  $ov: unchanged, skipped"
    continue
  fi
  # Remove the signature first so an interrupted build is redone next time.
  run "rm -f \"$sigfile\""
  run "rm -rf \"$ROOT/$ov\""         # idempotent: drops links from old ranges
  link_side "$ov/from_$A" "$ROOT/$ov/from_$A" "$aspec"
  link_side "$ov/from_$B" "$ROOT/$ov/from_$B" "$bspec"
  save_sig "$sigfile" "$sig"
done

# Build one run's _main folder: its missions, minus every seam line it contributes.
build_main() {   # run_name
  local name=$1
  local target="$ROOT/${name}_main" sigfile="$STATE/${name}_main.sig" sig
  local missions=${RUN_MISSIONS[$name]}
  EXPECTED[${name}_main]=1
  sig=$(main_sig "$name")
  if is_current "$target" "$sigfile" "$sig"; then
    echo "  ${name}_main: unchanged, skipped"
    return
  fi
  run "rm -f \"$sigfile\""
  run "rm -rf \"$target\""            # idempotent: only removes this generated tree
  run "mkdir -p \"$target\""
  local paths=() m
  for m in $missions; do
    [[ -d "$ROOT/$m" ]] || die "mission folder missing: $ROOT/$m"
    paths+=("$ROOT/$m")
  done
  run "cp -as ${paths[*]} \"$target/\""

  # Drop this run's seam photos. overlap_*/from_<name>/ holds a symlink to each
  # of them, and cp -as mirrored $ROOT under $target, so each copy to remove is
  # $target/<link target relative to ROOT> -- no need to search the tree.
  local ov dir link rel del=() gone=0
  for ov in ${RUN_OVERLAPS[$name]:-}; do
    dir="$ROOT/$ov/from_$name"
    if [[ $DRY -eq 1 ]]; then
      echo "  [dry-run] remove the seam photos linked in $ov/from_$name"
      continue
    fi
    [[ -d "$dir" ]] || die "overlap folder missing: $dir"
    while IFS= read -r -d '' link; do
      [[ "$link" == "${ROOT%/}"/* ]] || die "link in $dir points outside ROOT: $link"
      rel=${link#"${ROOT%/}"}; rel=${rel#"${rel%%[!/]*}"}   # strip ROOT + leading /'s
      if [[ -L "$target/$rel" ]]; then del+=("$target/$rel"); else gone=$((gone + 1)); fi
    done < <(find "$dir" -maxdepth 1 -type l -printf '%l\0')
  done
  [[ ${#del[@]} -gt 0 ]] && rm -f -- "${del[@]}"
  [[ $gone -gt 0 ]] && echo "  WARNING: $gone seam photos of $name were not found in $target"
  save_sig "$sigfile" "$sig"
  echo "  ${name}_main: built from [$missions] minus ${#del[@]} seam photos"
}

# Bash returns associative-array keys in hash order, so sort them for stable logs.
mapfile -t RUN_NAMES < <(printf '%s\n' "${!RUN_MISSIONS[@]}" | sort -V)

echo "[2/3] building per-run main folders ..."
for name in "${RUN_NAMES[@]}"; do build_main "$name"; done

# Folders from runs/seams no longer in the config are left alone; just report them.
stale=()
for d in "$ROOT"/overlap_* "$ROOT"/*_main; do
  [[ -d "$d" ]] || continue
  [[ -n "${EXPECTED[${d##*/}]:-}" ]] || stale+=("${d##*/}")
done
if [[ ${#stale[@]} -gt 0 ]]; then
  echo "NOTE: not in the current config (left untouched): ${stale[*]}"
fi

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
