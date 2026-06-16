# Moodle XML Import Utility

## Overview

The Question Bank app now includes a comprehensive Moodle XML import utility that allows you to import questions from Moodle's question bank XML export format.

## Features

### ✨ Core Capabilities

- **Upload & Parse**: Upload Moodle XML files and automatically parse questions
- **Preview Before Import**: Review all questions before importing them into your database
- **Smart Question Mapping**: Automatically maps Moodle question types to Question Bank types:
  - `multichoice` → MCQ (Multiple Choice)
  - `truefalse` → True/False  
  - `shortanswer` → Fill in the Blank
  - `numerical` → Fill in the Blank
  
### 📊 Advanced Features

- **Category Management**: Automatically creates topics from Moodle categories
- **Duplicate Detection**: Skip questions that already exist in your database
- **LaTeX Support**: Detects and preserves LaTeX mathematical notation
- **Image Handling**: Extracts embedded images and stores them as Odoo attachments
- **Rich Content**: Preserves HTML formatting, feedback, and explanations

## How to Use

### Step 1: Export from Moodle

1. In Moodle, go to **Question Bank**
2. Select the questions you want to export
3. Choose **Export** → **Moodle XML format**
4. Download the XML file

### Step 2: Import to Question Bank

1. In Odoo, navigate to **Question Bank** → **Import/Export** → **Import from Moodle**
2. Click **Upload** and select your Moodle XML file
3. Choose the **Default Subject** (required)
4. Optionally select a **Default Topic**
5. Configure import options:
   - ✅ **Create Categories as Topics**: Automatically create topics from Moodle categories
   - ✅ **Skip Duplicate Questions**: Avoid importing the same question twice

### Step 3: Preview Questions

1. Click **Parse XML** to analyze the uploaded file
2. Review the preview showing:
   - Question name and type
   - Category
   - LaTeX and image indicators
   - Answer preview
3. **Deselect** any questions you don't want to import
4. Click **View Details** (eye icon) to see full question content

### Step 4: Import

1. Click **Import Questions**
2. Wait for the import to complete
3. Review the success message showing:
   - Number of questions imported
   - Number of duplicates skipped

## Question Type Mapping

| Moodle Type | Question Bank Type | Notes |
|-------------|-------------------|-------|
| Multiple Choice | MCQ | Up to 6 options supported |
| True/False | True/False | Binary choice |
| Short Answer | Fill in the Blank | Accepts text answers |
| Numerical | Fill in the Blank | Accepts numeric answers |
| Essay | Essay | Long-form responses |

## Technical Details

### XML Structure Handled

The import utility parses the following Moodle XML elements:

- `<question type="...">` - Question type
- `<name><text>` - Question title
- `<questiontext><text>` - Question content (HTML)
- `<answer fraction="...">` - Answer options with correctness
- `<generalfeedback>` - Explanation/solution
- `<category>` - Question category
- `<file encoding="base64">` - Embedded images

### LaTeX Detection

The parser automatically detects LaTeX patterns:
- `$$...$$` - Display math
- `$...$` - Inline math
- `\begin{...}` and `\end{...}` - LaTeX environments
- `\frac{...}`, `\sqrt{...}`, etc. - Math functions

### Image Processing

Images embedded in Moodle XML are:
1. Extracted from `<file>` elements
2. Decoded from base64
3. Stored as Odoo `ir.attachment` records
4. Linked to the question record

### Duplicate Detection

Questions are considered duplicates if they have:
- Same `question_html` content
- Same `subject_id`

## Configuration

### Security

Access rights are controlled by:
- `group_qb_user` - Can import questions
- `group_qb_manager` - Full import permissions

### Models

- `qb.moodle.import` - Main wizard model (transient)
- `qb.moodle.import.line` - Preview lines (transient)

## Limitations

- Maximum 6 MCQ options per question (Moodle supports more)
- Essay questions are imported with minimal metadata
- Some Moodle-specific features may not transfer (e.g., hints, penalties)
- Complex question types (calculated, matching, etc.) may need manual review

## Troubleshooting

### Import Fails

- **Invalid XML**: Ensure the file is a valid Moodle XML export
- **Missing Subject**: You must select a default subject before importing
- **Permission Error**: Ensure you have the correct access rights

### Questions Not Showing

- Check the preview - they may have been deselected
- Verify duplicate detection didn't skip them
- Check filters in the Questions list view

### Images Not Displaying

- Images must be properly base64-encoded in the XML
- Check Odoo's attachment storage is configured correctly
- Verify file permissions in the filestore

## Future Enhancements

Planned features for future versions:
- Vector embeddings for question similarity search
- Bulk editing after preview
- Export to Moodle XML format
- Import from other formats (QTI, GIFT, etc.)
- Question validation and quality checks

## Support

For issues or questions:
1. Check the Odoo logs for detailed error messages
2. Verify your XML file is valid Moodle format
3. Test with a small sample file first
4. Contact your system administrator

---

**Version**: 1.0.0  
**Last Updated**: June 2026  
**Module**: question_bank
