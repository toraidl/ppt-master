#!/usr/bin/env python3
import re
import os

EMOJI_MAP = {
    '🧠': ('tabler-filled/bulb', 'Brain/Wisdom'),
    '❤️': ('tabler-filled/heart', 'Heart'),
    '💕': ('tabler-filled/heart', 'Hearts'),
    '⚡': ('tabler-filled/bolt', 'Lightning'),
    '💬': ('tabler-filled/message', 'Message'),
    '⚠️': ('tabler-filled/alert-triangle', 'Warning'),
    '📱': ('tabler-filled/device-mobile', 'Mobile'),
    '🔍': ('tabler-filled/search', 'Search'),
    '👇': ('tabler-filled/arrow-down-circle', 'Arrow Down'),
    '✅': ('tabler-filled/check', 'Check'),
    '❌': ('tabler-filled/circle-x', 'Cross'),
}

def replace_emoji_in_svg(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    modified = False
    
    for emoji, (icon_path, desc) in EMOJI_MAP.items():
        if emoji in content:
            pattern = rf'(<text[^>]*font-size=")(\d+)("[^>]*>)({re.escape(emoji)})(</text>)'
            
            def replacer(m):
                size = m.group(2)
                icon_size = int(int(size) * 0.8)
                
                x_match = re.search(r'x="(\d+)"', m.group(0))
                y_match = re.search(r'y="(\d+)"', m.group(0))
                
                if x_match and y_match:
                    x = int(x_match.group(1)) - icon_size // 2
                    y = int(y_match.group(1)) - icon_size
                    
                    return f'<use data-icon="{icon_path}" x="{x}" y="{y}" width="{icon_size}" height="{icon_size}" fill="#7C3AED"/>'
                return m.group(0)
            
            new_content = re.sub(pattern, replacer, content)
            if new_content != content:
                content = new_content
                modified = True
                print(f"  Replaced {emoji} -> {icon_path} in {os.path.basename(filepath)}")
    
    if modified:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    
    return modified

def main():
    project_dir = 'projects/intp_match_story_20260519/svg_output'
    
    print("Replacing emoji with SVG icons...")
    print("=" * 50)
    
    total_replaced = 0
    for filename in sorted(os.listdir(project_dir)):
        if filename.endswith('.svg'):
            filepath = os.path.join(project_dir, filename)
            if replace_emoji_in_svg(filepath):
                total_replaced += 1
    
    print("=" * 50)
    print(f"Done! Modified {total_replaced} files.")

if __name__ == '__main__':
    main()
