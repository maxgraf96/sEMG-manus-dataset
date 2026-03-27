# Publishing Checklist

## 1. Prepare The Local Data Package

Run the local build from the repository root:

```bash
./scripts/build_zenodo_package
```

This creates:

- `build/manifest.csv`
- `build/reports/qc_report.json`
- `build/reports/qc_report.md`
- `build/zenodo-package/`

## 2. Create The Zenodo Dataset Draft

On Zenodo:

1. Start a new upload.
2. Choose resource type `Dataset`.
3. Reserve a DOI.
4. Upload the files from `build/zenodo-package/`.

Recommended upload set:

- `semg-manus-dataset-v1.zip`
- `README.md`
- `CODEBOOK.md`
- `DATA_QUALITY.md`
- `manifest.csv`
- `checksums.txt`
- `LICENSE-data-CC-BY-4.0.txt`

## 3. Update The Repository Metadata

After the dataset DOI exists:

1. Update [README.md](/Users/max/Code/sEMG-manus-dataset/README.md) with the published dataset DOI and record URL.
2. Update [`.zenodo.json`](/Users/max/Code/sEMG-manus-dataset/.zenodo.json) and add the dataset DOI under `related_identifiers`.
3. Commit those metadata updates.

## 4. Publish The Public GitHub Repository

1. Create a GitHub repository.
2. Push this local repository.
3. Make the repository public.

The repository should contain only code, docs, and metadata. The raw `data/` tree remains ignored and local-only.

## 5. Link GitHub To Zenodo

1. Sign in to Zenodo with GitHub.
2. Enable this repository for release archiving.
3. Create the first GitHub release.

Zenodo will archive the release and mint the software DOI.

## 6. Cross-Link The Two Records

After the software DOI exists:

1. Add the software DOI to the Zenodo dataset record as a related identifier.
2. Replace `SOFTWARE_DOI_PENDING` in [README.md](/Users/max/Code/sEMG-manus-dataset/README.md).
3. Update [`.zenodo.json`](/Users/max/Code/sEMG-manus-dataset/.zenodo.json) if needed so future software releases remain linked to the dataset DOI.

## 7. Final Pre-Publish Checks

Before publishing, confirm:

- `git ls-files` does not contain `data/u_*`
- `./scripts/build_zenodo_package` completes successfully
- `build/zenodo-package/checksums.txt` exists
- `build/reports/qc_report.md` reports no unexpected gesture folders
- DOI placeholders are replaced
