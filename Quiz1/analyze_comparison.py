#!/usr/bin/env python3
"""
AI Model Performance Comparison - Quiz1
A simple script to analyze and visualize the comparison results.

Usage:
    python3 analyze_comparison.py                    # Basic statistics
    python3 analyze_comparison.py --chart scores      # Generate score chart
    python3 analyze_comparison.py --chart radar       # Generate radar chart
    python3 analyze_comparison.py --export excel      # Export to Excel
"""

import json
import sys
import argparse
from pathlib import Path

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'

def load_comparison_data():
    """Load the comparison result JSON file."""
    json_path = Path(__file__).parent / 'comparison_result.json'
    with open(json_path, 'r') as f:
        return json.load(f)

def print_header(text):
    """Print a formatted header."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text:^70}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.END}\n")

def print_ranking_table(data):
    """Print a ranking table of all models."""
    models = sorted(data['ai_models'], key=lambda x: x['weighted_score'], reverse=True)
    
    print(f"{Colors.BOLD}{'Rank':<6}{'Model':<25}{'Score':<10}{'Grade':<8}{Colors.END}")
    print("-" * 50)
    
    for i, model in enumerate(models, 1):
        score = model['weighted_score']
        if score >= 90:
            grade = f"{Colors.GREEN}A{Colors.END}"
        elif score >= 80:
            grade = f"{Colors.CYAN}B+{Colors.END}"
        elif score >= 70:
            grade = f"{Colors.CYAN}B{Colors.END}"
        elif score >= 60:
            grade = f"{Colors.YELLOW}C+{Colors.END}"
        elif score >= 50:
            grade = f"{Colors.YELLOW}C-{Colors.END}"
        elif score >= 40:
            grade = f"{Colors.RED}D{Colors.END}"
        else:
            grade = f"{Colors.RED}F{Colors.END}"
        
        rank_str = f"{Colors.GREEN}#{i}{Colors.END}" if i <= 3 else f"{i}"
        print(f"{rank_str:<6}{model['name']:<25}{score:<10.1f}{grade:<8}")

def print_category_breakdown(data):
    """Print breakdown by scoring category."""
    print_header("Score Breakdown by Category")
    
    categories = {
        'problem_recognition': 'Problem Recognition',
        'technical_accuracy': 'Technical Accuracy',
        'solution_quality': 'Solution Quality',
        'completeness': 'Completeness',
        'no_hallucinations': 'No Hallucinations',
        'documentation_usage': 'Documentation Usage'
    }
    
    max_scores = {
        'problem_recognition': 25,
        'technical_accuracy': 25,
        'solution_quality': 20,
        'completeness': 15,
        'no_hallucinations': 10,
        'documentation_usage': 5
    }
    
    models = sorted(data['ai_models'], key=lambda x: x['weighted_score'], reverse=True)
    
    for cat_key, cat_name in categories.items():
        print(f"\n{Colors.BOLD}{cat_name} (Max: {max_scores[cat_key]}){Colors.END}")
        print("-" * 60)
        
        for model in models[:5]:  # Top 5 only
            score = model['scores'][cat_key]
            max_score = max_scores[cat_key]
            bar_length = int((score / max_score) * 30)
            bar = '█' * bar_length + '░' * (30 - bar_length)
            
            color = Colors.GREEN if score >= max_score * 0.8 else Colors.YELLOW if score >= max_score * 0.6 else Colors.RED
            
            print(f"{model['name']:<25} {color}{score}/{max_score}{Colors.END} [{bar}]")

def print_statistics(data):
    """Print summary statistics."""
    print_header("Summary Statistics")
    
    models = data['ai_models']
    stats = data['summary_statistics']
    
    print(f"Total Models Evaluated: {Colors.BOLD}{stats['total_models']}{Colors.END}")
    print(f"Average Score: {Colors.BOLD}{stats['average_score']:.2f}/100{Colors.END}")
    print(f"Highest Score: {Colors.GREEN}{stats['highest_score']}/100{Colors.END}")
    print(f"Lowest Score: {Colors.RED}{stats['lowest_score']}/100{Colors.END}")
    print(f"Median Score: {Colors.BOLD}{stats['median_score']:.1f}/100{Colors.END}")
    print(f"Standard Deviation: {Colors.BOLD}{stats['standard_deviation']:.1f}{Colors.END}")
    
    print(f"\nPerfect Hallucination Scores: {Colors.GREEN}{stats['models_perfect_hallucination_score']}/8{Colors.END}")
    print(f"Models with Hallucinations: {Colors.RED}{stats['models_with_hallucinations']}/8{Colors.END}")

def print_hallucinations(data):
    """Print all hallucinations found."""
    print_header("Hallucinations and Assumptions")
    
    models = sorted(data['ai_models'], key=lambda x: x['weighted_score'], reverse=True)
    
    has_issues = False
    for model in models:
        if model['hallucinations'] or model['assumptions_without_evidence']:
            has_issues = True
            print(f"\n{Colors.RED}{model['name']}{Colors.END}")
            
            if model['hallucinations']:
                print(f"  {Colors.YELLOW}⚠ Hallucinations:{Colors.END}")
                for h in model['hallucinations']:
                    print(f"    • {h}")
            
            if model['assumptions_without_evidence']:
                print(f"  {Colors.YELLOW}⚠ Assumptions Without Evidence:{Colors.END}")
                for a in model['assumptions_without_evidence']:
                    print(f"    • {a}")
    
    if not has_issues:
        print(f"{Colors.GREEN}No hallucinations or unsupported assumptions found!{Colors.END}")

def print_key_findings(data):
    """Print key findings from the comparison."""
    print_header("Key Findings")
    
    findings = data['key_findings']
    for i, finding in enumerate(findings, 1):
        print(f"{i}. {finding}")

def generate_text_chart(data):
    """Generate a simple text-based score chart."""
    print_header("Score Chart")
    
    models = sorted(data['ai_models'], key=lambda x: x['weighted_score'], reverse=True)
    max_score = 100
    
    for model in models:
        score = model['weighted_score']
        bar_length = int((score / max_score) * 50)
        bar = '█' * bar_length + '░' * (50 - bar_length)
        
        if score >= 90:
            color = Colors.GREEN
        elif score >= 70:
            color = Colors.CYAN
        elif score >= 50:
            color = Colors.YELLOW
        else:
            color = Colors.RED
        
        print(f"{color}{score:5.1f}{Colors.END} {bar} {model['name']}")

def export_to_csv(data):
    """Export data to CSV format."""
    import csv
    
    models = sorted(data['ai_models'], key=lambda x: x['weighted_score'], reverse=True)
    
    output_path = Path(__file__).parent / 'comparison_export.csv'
    
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Rank', 'Model Name', 'Total Score', 'Problem Recognition',
            'Technical Accuracy', 'Solution Quality', 'Completeness',
            'No Hallucinations', 'Documentation Usage'
        ])
        
        for i, model in enumerate(models, 1):
            writer.writerow([
                i,
                model['name'],
                f"{model['weighted_score']:.1f}",
                model['scores']['problem_recognition'],
                model['scores']['technical_accuracy'],
                model['scores']['solution_quality'],
                model['scores']['completeness'],
                model['scores']['no_hallucinations'],
                model['scores']['documentation_usage']
            ])
    
    print(f"{Colors.GREEN}✓{Colors.END} Data exported to: {output_path}")

def main():
    parser = argparse.ArgumentParser(description='Analyze AI model performance comparison')
    parser.add_argument('--chart', choices=['scores', 'radar'], help='Generate chart')
    parser.add_argument('--export', choices=['excel', 'csv'], help='Export data')
    parser.add_argument('--top', type=int, default=8, help='Number of top models to show (default: 8)')
    
    args = parser.parse_args()
    
    # Load data
    data = load_comparison_data()
    
    # Print header
    print_header(f"AI Model Performance Comparison - Quiz1")
    print(f"{data['quiz_metadata']['topic']}")
    print(f"Date: {data['quiz_metadata']['date']}")
    
    # Print ranking table
    print_ranking_table(data)
    
    # Print statistics
    print_statistics(data)
    
    # Print category breakdown (top 5)
    print_category_breakdown(data)
    
    # Print hallucinations
    print_hallucinations(data)
    
    # Print key findings
    print_key_findings(data)
    
    # Generate chart if requested
    if args.chart == 'scores':
        generate_text_chart(data)
    elif args.chart == 'radar':
        print(f"\n{Colors.YELLOW}Note: For radar charts, import the CSV file into Excel or use a visualization tool.{Colors.END}")
    
    # Export data if requested
    if args.export:
        export_to_csv(data)

if __name__ == '__main__':
    main()
