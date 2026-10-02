# Zotero CSL Field Code Management in DOCX

This reference guide explains how Zotero embeds dynamic citation field codes in Microsoft Word (`.docx`) files, how to inspect, inject, and validate them without unlinking or corrupting the live connection.

---

## 1. Anatomy of Zotero CSL Field Codes

Zotero stores citations in Word using standard OpenXML complex field characters (`<w:fldChar>`) containing a `CSL_CITATION` JSON instruction:

```xml
<!-- Run 1: Begin Field -->
<w:r>
  <w:fldChar w:fldCharType="begin"/>
</w:r>

<!-- Run 2: Zotero Instruction Text with CSL JSON payload -->
<w:r>
  <w:instrText xml:space="preserve"> ADDIN ZOTERO_ITEM CSL_CITATION {
    "citationID": "zotero_mobilenetv3_x82f1",
    "properties": {
      "formattedCitation": "[39]",
      "plainCitation": "[39]",
      "dontUpdate": false
    },
    "citationItems": [
      {
        "id": 1042,
        "uris": [
          "http://zotero.org/users/local/7x91k2/items/A94KF20"
        ],
        "itemData": {
          "id": 1042,
          "type": "paper-conference",
          "title": "Searching for MobileNetV3",
          "container-title": "IEEE/CVF International Conference on Computer Vision (ICCV)",
          "DOI": "10.1109/ICCV.2019.00140",
          "author": [
            {"family": "Howard", "given": "Andrew"},
            {"family": "Sandler", "given": "Mark"}
          ],
          "issued": {
            "date-parts": [[2019, 10]]
          }
        }
      }
    ],
    "schema": "https://github.com/citation-style-language/schema/raw/master/csl-citation.json"
  } </w:instrText>
</w:r>

<!-- Run 3: Field Separator -->
<w:r>
  <w:fldChar w:fldCharType="separate"/>
</w:r>

<!-- Run 4: Visible In-Text Citation Display -->
<w:r>
  <w:t>[39]</w:t>
</w:r>

<!-- Run 5: End Field -->
<w:r>
  <w:fldChar w:fldCharType="end"/>
</w:r>
```

At the end of the document, the bibliography section is anchored with:
```xml
<w:p>
  <w:r><w:fldChar w:fldCharType="begin"/></w:r>
  <w:r><w:instrText xml:space="preserve"> ADDIN ZOTERO_BIBL {"uncited":[],"omitted":[],"custom":[]} CSL_BIBLIOGRAPHY </w:instrText></w:r>
  <w:r><w:fldChar w:fldCharType="separate"/></w:r>
  <!-- Generated bibliography items -->
  <w:r><w:fldChar w:fldCharType="end"/></w:r>
</w:p>
```

---

## 2. Available Scripts

All scripts are located in `scripts/zotero/`:

### A. Inspect Citations
Scans a `.docx` or unpacked directory, parses all CSL JSON payloads, and prints formatted citations:
```bash
python scripts/zotero/inspect_zotero.py manuscript.docx
python scripts/zotero/inspect_zotero.py manuscript.docx --json
python scripts/zotero/inspect_zotero.py manuscript.docx --export-bib library.bib
```

### B. Inject New Citation
Injects a native Zotero CSL field code right after (or before) an anchor string:
```bash
python scripts/zotero/inject_zotero.py manuscript.docx \
  --after "MobileNetV3" \
  --citation-text "[39]" \
  --title "Searching for MobileNetV3" \
  --authors "Howard, Andrew; Sandler, Mark" \
  --year 2019 \
  --venue "ICCV" \
  --doi "10.1109/ICCV.2019.00140" \
  -o updated_manuscript.docx
```

### C. Validate Integrity
Checks that all `begin`, `separate`, and `end` delimiters match, validates JSON payloads, and checks for bibliography anchors:
```bash
python scripts/zotero/validate_zotero.py updated_manuscript.docx
```

---

## 3. Human-in-the-Loop Refresh in Microsoft Word

After editing or injecting citations:
1. Open the `.docx` file in **Microsoft Word** (ensure Zotero desktop app is open).
2. Go to the **Zotero** tab in the Word Ribbon.
3. Click **Refresh** (circular arrows icon).
4. Zotero re-indexes all field codes, updates citation numbers/styles (IEEE/APA/Harvard), and recalculates the bibliography automatically.
