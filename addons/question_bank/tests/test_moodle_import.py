#!/usr/bin/env python3
"""
Test script for Moodle XML Import
Demonstrates the XML parsing capabilities without needing Odoo running
"""

import xml.etree.ElementTree as ET
import re
import html

def clean_html(text):
    """Clean HTML and preserve formatting"""
    if not text:
        return ''
    return html.unescape(text).strip()

def detect_latex(text):
    """Detect if text contains LaTeX"""
    if not text:
        return False
    latex_patterns = [
        r'\$\$.*?\$\$',  # Display math
        r'\$.*?\$',      # Inline math
        r'\\begin\{.*?\}',
        r'\\frac\{',
        r'\\sqrt\{',
    ]
    for pattern in latex_patterns:
        if re.search(pattern, text):
            return True
    return False

def parse_moodle_xml(xml_file_path):
    """Parse a Moodle XML file and extract question information"""
    
    try:
        tree = ET.parse(xml_file_path)
        root = tree.getroot()
        
        questions = []
        
        for question_elem in root.findall('question'):
            qtype = question_elem.get('type')
            
            # Skip category questions
            if qtype == 'category':
                continue
            
            # Extract basic info
            name_elem = question_elem.find('name/text')
            question_text_elem = question_elem.find('questiontext/text')
            
            if name_elem is None or question_text_elem is None:
                continue
            
            name = name_elem.text or 'Untitled'
            question_text = clean_html(question_text_elem.text or '')
            
            # Extract category
            category = ''
            category_elem = question_elem.find('.//category/text')
            if category_elem is not None:
                category = category_elem.text or ''
            
            # Detect LaTeX
            has_latex = detect_latex(question_text)
            
            # Parse answers
            answers = []
            for answer_elem in question_elem.findall('answer'):
                fraction = float(answer_elem.get('fraction', 0))
                text_elem = answer_elem.find('text')
                if text_elem is not None:
                    answer_text = clean_html(text_elem.text or '')
                    answers.append({
                        'text': answer_text,
                        'is_correct': fraction > 0
                    })
            
            # Extract feedback
            feedback = ''
            feedback_elem = question_elem.find('generalfeedback/text')
            if feedback_elem is not None:
                feedback = clean_html(feedback_elem.text or '')
            
            questions.append({
                'name': name,
                'type': qtype,
                'category': category,
                'question_text': question_text[:100] + '...' if len(question_text) > 100 else question_text,
                'has_latex': has_latex,
                'answers_count': len(answers),
                'correct_answers': len([a for a in answers if a['is_correct']]),
                'has_feedback': bool(feedback)
            })
        
        return questions
        
    except ET.ParseError as e:
        print(f"Error parsing XML: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error: {e}")
        return []


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python test_moodle_import.py <xml_file_path>")
        print("\nExample:")
        print("  python test_moodle_import.py /path/to/moodle_export.xml")
        sys.exit(1)
    
    xml_file = sys.argv[1]
    
    print(f"Parsing Moodle XML file: {xml_file}")
    print("=" * 80)
    
    questions = parse_moodle_xml(xml_file)
    
    if not questions:
        print("No questions found or error parsing file.")
        sys.exit(1)
    
    print(f"\nFound {len(questions)} question(s)\n")
    
    for idx, q in enumerate(questions, 1):
        print(f"{idx}. {q['name']}")
        print(f"   Type: {q['type']}")
        if q['category']:
            print(f"   Category: {q['category']}")
        print(f"   Question: {q['question_text']}")
        print(f"   Answers: {q['answers_count']} ({q['correct_answers']} correct)")
        print(f"   LaTeX: {'Yes' if q['has_latex'] else 'No'}")
        print(f"   Feedback: {'Yes' if q['has_feedback'] else 'No'}")
        print()
    
    print("=" * 80)
    print(f"Summary: {len(questions)} questions ready for import")
