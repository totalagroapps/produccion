import os
import re

templates_dir = r"C:\Users\CALIDADINV\OneDrive\Documentos\produccion_server_pg\templates"

viewport_tag = '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
responsive_css = """
<style>
/* Base Responsive Styles */
@media (max-width: 768px) {
    .container {
        padding: 15px !important;
    }
    .card, .box, .panel {
        padding: 12px !important;
        margin-bottom: 15px !important;
    }
    .grid {
        grid-template-columns: 1fr !important;
    }
    input, select, button, textarea {
        width: 100% !important;
        box-sizing: border-box !important;
        margin-bottom: 8px !important;
    }
    table {
        display: block !important;
        width: 100% !important;
        overflow-x: auto !important;
        white-space: nowrap !important;
    }
    th, td {
        padding: 8px !important;
        font-size: 13px !important;
    }
    h2, h3 {
        font-size: 1.2rem !important;
    }
}
</style>
"""

for filename in os.listdir(templates_dir):
    if not filename.endswith('.html'):
        continue
        
    filepath = os.path.join(templates_dir, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Check if file has a <head> section
    if '<head>' in content or '</head>' in content:
        changed = False
        
        # Insert viewport if missing
        if 'name="viewport"' not in content:
            content = content.replace('<head>', '<head>\n' + viewport_tag)
            changed = True
            
        # Add basic responsive styles before </head> if not base.html
        # base.html already has global media queries
        if filename not in ['base.html'] and 'max-width: 768px' not in content and 'max-width: 640px' not in content:
            content = content.replace('</head>', responsive_css + '\n</head>')
            changed = True
            
        if changed:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Updated {filename}")
    else:
        # Files without <head> are probably partials or extend base.html
        pass

print("Done updating templates for responsiveness.")
