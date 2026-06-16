# Technical Architecture: Moodle Import Utility

## System Design

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     User Interface Layer                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Upload Form  │→ │Preview Table │→ │Import Result │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                    Business Logic Layer                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │         QbMoodleImport (Transient Model)            │   │
│  │  • action_parse_xml()                                │   │
│  │  • action_import_questions()                         │   │
│  │  • _parse_question()                                 │   │
│  │  • _parse_multichoice/truefalse/shortanswer()       │   │
│  │  • _detect_latex()                                   │   │
│  │  • _extract_images()                                 │   │
│  │  • _clean_html()                                     │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │      QbMoodleImportLine (Transient Model)           │   │
│  │  • Preview data for each question                    │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                     Data Storage Layer                       │
│  ┌────────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │  qb.question   │  │qb.question.  │  │ ir.attachment  │  │
│  │                │  │   option     │  │   (images)     │  │
│  │  • Main Q data │  │ • MCQ options│  │ • Image files  │  │
│  │  • HTML content│  │ • Correct?   │  │ • Base64 data  │  │
│  │  • LaTeX       │  │              │  │                │  │
│  └────────────────┘  └──────────────┘  └────────────────┘  │
│  ┌────────────────┐  ┌──────────────┐                      │
│  │  qb.subject    │  │  qb.topic    │                      │
│  │  (existing)    │  │ (created)    │                      │
│  └────────────────┘  └──────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Upload Phase

```python
User uploads XML file
    ↓
File stored as binary in qb.moodle.import.xml_file
    ↓
Base64 decoded in memory
    ↓
Parsed with xml.etree.ElementTree
```

### 2. Parse Phase

```python
action_parse_xml() triggered
    ↓
For each <question> element:
    ↓
    _parse_question()
        ↓
        ├→ Extract name, text, category
        ├→ _detect_latex(text)
        ├→ _extract_images(elem)
        ├→ Parse answers by type:
        │   ├→ _parse_multichoice()
        │   ├→ _parse_truefalse()
        │   └→ _parse_shortanswer()
        ├→ Extract feedback
        └→ Create preview_line record
    ↓
Display preview in tree view
```

### 3. Import Phase

```python
action_import_questions() triggered
    ↓
For each selected preview line:
    ↓
    Check for duplicates (optional)
    ↓
    Determine/create topic from category
    ↓
    Create qb.question record
    ↓
    If MCQ: Create qb.question.option records
    ↓
    If images: Create ir.attachment records
    ↓
    Handle errors gracefully (continue with next)
    ↓
Return statistics (imported/skipped)
```

## Model Structure

### QbMoodleImport (Transient)

```python
{
    'xml_file': Binary (required),
    'filename': Char,
    'state': Selection ['upload', 'preview', 'done'],
    'subject_id': Many2one('qb.subject', required),
    'topic_id': Many2one('qb.topic'),
    'create_categories_as_topics': Boolean (default=True),
    'skip_duplicates': Boolean (default=True),
    'preview_line_ids': One2many('qb.moodle.import.line'),
    'total_questions': Integer (computed),
    'selected_questions': Integer (computed),
}
```

### QbMoodleImportLine (Transient)

```python
{
    'import_id': Many2one('qb.moodle.import', required),
    'selected': Boolean (default=True),
    'name': Char,  # Question title
    'question_text': Text,  # Question content
    'question_type': Selection ['mcq', 'true_false', 'fill_blank'],
    'moodle_type': Char,  # Original Moodle type
    'category': Char,
    'has_latex': Boolean,
    'has_images': Boolean,
    'images_data': Text,  # JSON string
    'answers_preview': Text,  # Formatted for display
    'answers_json': Text,  # Full answer data
    'correct_answer': Char,
    'feedback': Text,
}
```

## Key Algorithms

### LaTeX Detection

```python
PATTERNS = [
    r'\$\$.*?\$\$',      # Display: $$x^2$$
    r'\$.*?\$',          # Inline: $x$
    r'\\begin\{.*?\}',   # Environment
    r'\\end\{.*?\}',     # Environment
    r'\\frac\{',         # Fraction
    r'\\sqrt\{',         # Square root
    r'\\text\{',         # Text
]

def _detect_latex(text):
    for pattern in PATTERNS:
        if re.search(pattern, text):
            return True
    return False
```

### Image Extraction

```python
def _extract_images(text_elem):
    images = []
    for file_elem in text_elem.findall('.//file'):
        if file_elem.get('encoding') == 'base64':
            images.append({
                'filename': file_elem.get('name'),
                'data': file_elem.text,  # Already base64
                'encoding': 'base64'
            })
    return images
```

### Answer Parsing (MCQ)

```python
def _parse_multichoice(question_elem):
    answers = []
    correct = []
    
    for answer_elem in question_elem.findall('answer'):
        fraction = float(answer_elem.get('fraction', 0))
        text = _clean_html(answer_elem.find('text').text)
        
        answers.append({
            'text': text,
            'fraction': fraction,
            'is_correct': fraction > 0
        })
        
        if fraction > 0:
            correct.append(text)
    
    return answers, ', '.join(correct)
```

### Duplicate Detection

```python
def check_duplicate(line, subject_id):
    existing = env['qb.question'].search([
        ('question_html', '=', line.question_text),
        ('subject_id', '=', subject_id)
    ], limit=1)
    return bool(existing)
```

## Database Schema

### Questions Storage

```sql
-- Main question record
INSERT INTO qb_question (
    name,                 -- Question title
    question_html,        -- HTML content with LaTeX
    question_type,        -- 'mcq', 'true_false', 'fill_blank'
    subject_id,           -- FK to qb_subject
    topic_id,             -- FK to qb_topic
    explanation,          -- Feedback from Moodle
    difficulty,           -- Default: 'medium'
    state                 -- Default: 'draft'
);

-- MCQ options (if applicable)
INSERT INTO qb_question_option (
    question_id,          -- FK to qb_question
    sequence,             -- Order: 1, 2, 3...
    option_text,          -- HTML answer text
    is_correct            -- Boolean
);

-- Embedded images
INSERT INTO ir_attachment (
    name,                 -- Filename
    datas,                -- Base64 image data
    res_model,            -- 'qb.question'
    res_id,               -- Question ID
    type                  -- 'binary'
);
```

## Performance Optimization

### Memory Management
- Transient models auto-cleanup
- Process questions in batches (no explicit batching, handled by ORM)
- Images stored as attachments (not in question record)

### Database Optimization
- Indexes on question_html for duplicate search
- Indexes on subject_id and topic_id for filtering
- Use limit=1 in duplicate searches

### Error Handling
```python
for line in selected_lines:
    try:
        # Import logic
        imported_count += 1
    except Exception as e:
        # Log error but continue
        continue  # Don't fail entire import
```

## Security Considerations

### Input Validation
- XML structure validated before parsing
- HTML sanitization disabled (we want rich content)
- Base64 decoding with try/except
- File size limits (Odoo default)

### Access Control
```csv
# Only QB users can import
access_qb_moodle_import_user,qb.moodle.import user,model_qb_moodle_import,group_qb_user,1,1,1,1
```

### SQL Injection Prevention
- All queries through ORM
- No raw SQL execution
- Parameters properly escaped

## Testing Strategy

### Unit Tests (Standalone)
```python
# tests/test_moodle_import.py
def test_parse_xml():
    questions = parse_moodle_xml('sample.xml')
    assert len(questions) == 5
    assert questions[0]['has_latex'] == True
```

### Integration Tests
```python
# tests/test_import_integration.py
def test_full_import_flow():
    wizard = env['qb.moodle.import'].create({
        'xml_file': base64_sample,
        'subject_id': subject.id,
    })
    wizard.action_parse_xml()
    assert len(wizard.preview_line_ids) == 5
    wizard.action_import_questions()
    assert env['qb.question'].search_count([]) == 5
```

## Extension Points

### Adding New Question Types

```python
def _parse_question(self, question_elem):
    qtype = question_elem.get('type')
    
    if qtype == 'multichoice':
        answers, correct = self._parse_multichoice(question_elem)
    elif qtype == 'truefalse':
        answers, correct = self._parse_truefalse(question_elem)
    # Add new type here:
    elif qtype == 'matching':
        answers, correct = self._parse_matching(question_elem)
    
    # Map to Odoo type
    odoo_type = self._map_question_type(qtype)
```

### Custom Image Processing

```python
def _process_image(self, image_data):
    # Override to add:
    # - Image compression
    # - Format conversion
    # - Dimension validation
    # - OCR text extraction
    return processed_data
```

### Vector Embedding Integration

```python
def action_import_questions(self):
    # ... existing import logic ...
    
    # Add after question creation:
    if self.env.context.get('generate_embeddings'):
        self._generate_embeddings(question)

def _generate_embeddings(self, question):
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    text = f"{question.question_html} {question.explanation}"
    embedding = model.encode(text)
    
    # Store in pgvector or custom table
    question.embedding = embedding.tolist()
```

## Monitoring & Logging

### Import Metrics
```python
_logger.info(f"Import started: {len(selected_lines)} questions")
_logger.info(f"Import complete: {imported_count} success, {skipped_count} skipped")
_logger.error(f"Import error on question '{line.name}': {str(e)}")
```

### Performance Tracking
- Log parse time: `action_parse_xml()`
- Log import time: `action_import_questions()`
- Track database query count
- Monitor memory usage for large imports

## Future Enhancements

### Phase 2
- Batch processing for 1000+ questions
- Progress bar during import
- Validation rules before import
- Preview statistics (question types, difficulties)

### Phase 3
- Export to Moodle XML
- Import from QTI, GIFT, Aiken formats
- Question deduplication by similarity
- Auto-tagging based on content

### Phase 4
- Vector similarity search
- AI-powered question quality scoring
- Automatic difficulty estimation
- Smart categorization

---

**Architecture Version**: 1.0.0  
**Last Updated**: June 2026  
**Author**: ShiningAce Development Team
