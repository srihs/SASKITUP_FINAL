#!/usr/bin/env python3
"""
Simple validation test for SAS layout fixes
Tests template syntax and JavaScript file validity
"""

import os
import re
import json


def validate_template_changes():
    """Validate the SAS template changes"""
    results = {
        "template_validation": {},
        "javascript_validation": {},
        "issues_found": [],
        "fixes_verified": []
    }

    # Test 1: Validate SAS template structure
    template_path = "/Users/sas/Repos/SASKITUP/template/clubs/sas_product_detail.html"

    if os.path.exists(template_path):
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()

        # Check Fix 1: Color swatches positioned under Available Colors label
        color_section_match = re.search(
            r'<h6[^>]*>Available Colors</h6>\s*</div>\s*<div class="color-swatches"',
            template_content,
            re.DOTALL
        )

        if color_section_match:
            results["fixes_verified"].append("✅ Color swatches positioned under 'Available Colors' label")
            results["template_validation"]["colors_positioned_correctly"] = True
        else:
            results["issues_found"].append("❌ Color swatches not properly positioned under label")
            results["template_validation"]["colors_positioned_correctly"] = False

        # Check Fix 2: "Select Size" label removed
        select_size_pattern = r'<h6[^>]*>Select Size</h6>'
        select_size_matches = re.findall(select_size_pattern, template_content)

        if len(select_size_matches) == 0:
            results["fixes_verified"].append("✅ 'Select Size' label successfully removed")
            results["template_validation"]["select_size_removed"] = True
        else:
            results["issues_found"].append(f"❌ Found {len(select_size_matches)} 'Select Size' labels in template")
            results["template_validation"]["select_size_removed"] = False

        # Check basic template structure
        required_elements = [
            r'<div class="color-options mb-4">',
            r'<div class="size-options mb-4">',
            r'<div class="color-swatches">',
            r'<div class="size-buttons">'
        ]

        structure_valid = True
        for element in required_elements:
            if not re.search(element, template_content):
                results["issues_found"].append(f"❌ Missing required element: {element}")
                structure_valid = False

        results["template_validation"]["structure_valid"] = structure_valid
        if structure_valid:
            results["fixes_verified"].append("✅ Template structure is valid")

    else:
        results["issues_found"].append("❌ SAS template file not found")
        results["template_validation"]["file_exists"] = False

    # Test 2: Validate JavaScript changes
    js_path = "/Users/sas/Repos/SASKITUP/static/assets/js/product-variations.js"

    if os.path.exists(js_path):
        with open(js_path, 'r', encoding='utf-8') as f:
            js_content = f.read()

        # Check Fix 3: Stock text logic updated
        stock_text_logic = re.search(
            r'const isValidColorName.*?const headerText.*?Size Inventory',
            js_content,
            re.DOTALL
        )

        if stock_text_logic:
            results["fixes_verified"].append("✅ Stock text logic updated to handle 'Bottle' case")
            results["javascript_validation"]["stock_text_fixed"] = True
        else:
            results["issues_found"].append("❌ Stock text fix not found in JavaScript")
            results["javascript_validation"]["stock_text_fixed"] = False

        # Check for SAS-specific logic in size variations
        sas_size_logic = re.search(
            r'this\.productType === [\'"]sas[\'"].*?titleHtml.*?=.*?[\'"][\'"]',
            js_content,
            re.DOTALL
        )

        if sas_size_logic:
            results["fixes_verified"].append("✅ SAS-specific size label logic implemented")
            results["javascript_validation"]["sas_size_logic"] = True
        else:
            results["issues_found"].append("❌ SAS-specific size logic not found")
            results["javascript_validation"]["sas_size_logic"] = False

        # Check for color structure preservation
        color_preserve_logic = re.search(
            r'let swatchContainer = container\.querySelector.*?color-swatches.*?Clear existing swatches but preserve',
            js_content,
            re.DOTALL
        )

        if color_preserve_logic:
            results["fixes_verified"].append("✅ Color structure preservation logic found")
            results["javascript_validation"]["color_preserve_logic"] = True
        else:
            results["issues_found"].append("❌ Color structure preservation logic missing")
            results["javascript_validation"]["color_preserve_logic"] = False

        # Basic JavaScript syntax check (look for obvious syntax errors)
        syntax_issues = []

        # Check for unmatched braces (basic check)
        open_braces = js_content.count('{')
        close_braces = js_content.count('}')
        if open_braces != close_braces:
            syntax_issues.append(f"Unmatched braces: {open_braces} open, {close_braces} close")

        # Check for unmatched parentheses (basic check)
        open_parens = js_content.count('(')
        close_parens = js_content.count(')')
        if open_parens != close_parens:
            syntax_issues.append(f"Unmatched parentheses: {open_parens} open, {close_parens} close")

        if syntax_issues:
            results["issues_found"].extend([f"❌ JavaScript syntax issue: {issue}" for issue in syntax_issues])
            results["javascript_validation"]["syntax_valid"] = False
        else:
            results["fixes_verified"].append("✅ JavaScript syntax appears valid")
            results["javascript_validation"]["syntax_valid"] = True

    else:
        results["issues_found"].append("❌ JavaScript file not found")
        results["javascript_validation"]["file_exists"] = False

    return results


def main():
    print("🚀 Starting SAS Layout Validation Test...")

    results = validate_template_changes()

    print("✅ Validation completed!")

    # Display results
    print("\n" + "="*60)
    print("SAS LAYOUT VALIDATION RESULTS")
    print("="*60)

    print(f"\n✅ Fixes Verified: {len(results['fixes_verified'])}")
    print(f"❌ Issues Found: {len(results['issues_found'])}")

    if results['fixes_verified']:
        print("\n🎉 VERIFIED FIXES:")
        for fix in results['fixes_verified']:
            print(f"   {fix}")

    if results['issues_found']:
        print("\n⚠️  ISSUES FOUND:")
        for issue in results['issues_found']:
            print(f"   {issue}")

    # Detailed breakdown
    print("\n📊 DETAILED VALIDATION:")

    print("\n📄 Template Validation:")
    for key, value in results['template_validation'].items():
        status = "✅ PASS" if value else "❌ FAIL"
        print(f"   {key.replace('_', ' ').title()}: {status}")

    print("\n🔧 JavaScript Validation:")
    for key, value in results['javascript_validation'].items():
        status = "✅ PASS" if value else "❌ FAIL"
        print(f"   {key.replace('_', ' ').title()}: {status}")

    # Summary
    total_template_checks = len(results['template_validation'])
    passed_template_checks = sum(results['template_validation'].values())

    total_js_checks = len(results['javascript_validation'])
    passed_js_checks = sum(results['javascript_validation'].values())

    print(f"\n🎯 SUMMARY:")
    print(f"   Template: {passed_template_checks}/{total_template_checks} checks passed")
    print(f"   JavaScript: {passed_js_checks}/{total_js_checks} checks passed")
    print(f"   Overall: {len(results['fixes_verified'])} fixes verified, {len(results['issues_found'])} issues found")

    # Save results
    with open('/Users/sas/Repos/SASKITUP/layout_validation_results.json', 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n💾 Results saved to: /Users/sas/Repos/SASKITUP/layout_validation_results.json")

    return results


if __name__ == "__main__":
    main()