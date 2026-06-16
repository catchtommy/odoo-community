# Quick Start Guide: Import Questions from Moodle

## 📋 Prerequisites

- Odoo Question Bank module installed
- At least one Subject created
- Moodle XML export file ready

## 🚀 Step-by-Step Instructions

### Step 1: Access the Import Wizard

```
Main Menu → Question Bank → Import/Export → Import from Moodle
```

### Step 2: Configure Import Settings

**Upload Tab:**
1. Click **Browse** and select your Moodle XML file
2. Select **Default Subject** (required) - where questions will be stored
3. Optionally select **Default Topic** - assign all questions to this topic
4. Configure options:
   - ☑️ **Create Categories as Topics** - Auto-create topics from Moodle categories
   - ☑️ **Skip Duplicate Questions** - Avoid importing duplicates

### Step 3: Parse and Preview

1. Click **Parse XML** button
2. System analyzes the file and shows preview
3. Review the summary: **"Found X question(s)"**
4. Preview table displays:
   - ✓ **Checkbox** - Select/deselect for import
   - **Question Name** - Title from Moodle
   - **Type** - MCQ, True/False, Fill in the Blank
   - **Category** - Original Moodle category
   - **LaTeX** - Indicator if contains math
   - **Images** - Indicator if contains images
   - **Correct Answer** - Quick preview
   - **👁 View Details** - See full question

### Step 4: Review Individual Questions

1. Click **👁 eye icon** on any question
2. Popup shows:
   - Full question text (HTML formatted)
   - All answer options with ✓/○ markers
   - Correct answer highlighted
   - Feedback/explanation
   - LaTeX and image indicators
3. Click **Close** to return to list

### Step 5: Select Questions to Import

- **Import all**: Keep all checkboxes selected
- **Skip some**: Uncheck unwanted questions
- **Counter shows**: "Selected X / Y"

### Step 6: Import

1. Click **Import Questions** button
2. System processes each selected question:
   - Creates question record
   - Stores answer options
   - Attaches images
   - Maps categories to topics
3. Success notification shows:
   - "Successfully imported X question(s)"
   - "Skipped Y duplicate(s)" (if any)

### Step 7: Verify Import

1. Go to **Question Bank → Questions**
2. Filter by subject to see imported questions
3. Open a question to verify:
   - Question text preserved
   - LaTeX renders correctly
   - Images display
   - Answers stored correctly

## 📝 Sample Moodle XML Structure

```xml
<?xml version="1.0" encoding="UTF-8"?>
<quiz>
  <question type="multichoice">
    <name><text>Question Title</text></name>
    <questiontext format="html">
      <text><![CDATA[<p>Question content with $LaTeX$</p>]]></text>
    </questiontext>
    <answer fraction="100">
      <text><![CDATA[<p>Correct answer</p>]]></text>
    </answer>
    <answer fraction="0">
      <text><![CDATA[<p>Wrong answer</p>]]></text>
    </answer>
    <generalfeedback>
      <text><![CDATA[<p>Explanation here</p>]]></text>
    </generalfeedback>
  </question>
</quiz>
```

## 🎯 Tips for Best Results

### Before Exporting from Moodle
- Clean up question names (they become titles in Odoo)
- Organize questions in categories (become topics)
- Review LaTeX syntax is correct
- Ensure images are embedded properly

### In the Import Wizard
- Use **Create Categories as Topics** if your Moodle has good category structure
- Use **Skip Duplicates** for incremental imports
- Always preview before importing
- Check LaTeX and image indicators

### After Import
- Review a few questions to verify quality
- Test LaTeX rendering
- Check image attachments
- Adjust topics/tags as needed
- Set appropriate difficulty levels

## ⚠️ Common Issues

### XML Parse Error
- **Cause**: Invalid or corrupted XML file
- **Solution**: Re-export from Moodle, ensure complete file

### No Questions Found
- **Cause**: Empty file or wrong format
- **Solution**: Verify it's a Moodle XML question bank export

### Images Not Showing
- **Cause**: Images not base64-encoded in XML
- **Solution**: Check Moodle export settings include embedded files

### All Questions Skipped
- **Cause**: Duplicate detection found matches
- **Solution**: Uncheck "Skip Duplicates" or delete existing questions first

### LaTeX Not Rendering
- **Cause**: Missing MathJax configuration
- **Solution**: Ensure MathJax is loaded in Question Bank views

## 📊 Question Type Mapping

| From Moodle | To Odoo | Notes |
|-------------|---------|-------|
| Multiple Choice | MCQ | ≤6 options |
| True/False | True/False | Binary |
| Short Answer | Fill in the Blank | Text |
| Numerical | Fill in the Blank | Numbers |

## 🔒 Required Permissions

- **Question Bank User**: Can import questions
- **Question Bank Manager**: Full import rights

## 📞 Need Help?

1. Check logs in Odoo for detailed errors
2. Test with sample file first (see `/tests/sample_moodle_questions.xml`)
3. Verify file is valid XML
4. Review MOODLE_IMPORT_README.md for technical details

---

**Happy Importing! 🎉**
