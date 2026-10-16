from backend.services.design_extractor import extract_design_tokens
from backend.services.design_cache import get_cached_design, set_cached_design

def generate_design_md(tokens: dict) -> str:
    """將 Design Tokens 轉換為 DESIGN.md Markdown 格式"""
    domain = tokens.get("domain", "target-domain")
    typography = tokens.get("typography", {})
    colors = tokens.get("colors", {})
    components = tokens.get("components", {})
    btn = components.get("button", {})
    inp = components.get("input", {})
    card = components.get("card", {})

    return f"""# {domain} — Extracted Design System

## Visual Theme & Atmosphere
Clean, professional interface. Extracted from live site analysis.

## Color Palette & Roles
| Role | Hex | Usage |
|------|-----|-------|
| Background | {colors.get('background')} | 頁面主背景色 |
| Text Primary | {colors.get('text_primary')} | 主要文字色 |
| Primary Action | {colors.get('primary_action')} | CTA 按鈕背景色 |
| Primary Action Text | {colors.get('primary_action_text')} | CTA 按鈕文字色 |
| Input Border | {colors.get('input_border')} | 輸入框邊框顏色 |

## Typography Rules
- **Body Font:** `{typography.get('font_family')}`
- **Heading Font:** `{typography.get('heading_font')}`

## Component Stylings

### Buttons
- Border Radius: `{btn.get('border_radius')}`
- Box Shadow: `{btn.get('box_shadow')}`
- Padding: `{btn.get('padding')}`
- Font Weight: `{btn.get('font_weight')}`
- Font Size: `{btn.get('font_size')}`

### Input Fields
- Border Radius: `{inp.get('border_radius')}`
- Border Color: `{inp.get('border_width')} solid {colors.get('input_border')}`
- Padding: `{inp.get('padding')}`
- Font Size: `{inp.get('font_size')}`

### Cards / Containers
- Border Radius: `{card.get('border_radius')}`
- Box Shadow: `{card.get('box_shadow')}`

## Do's and Don'ts
- ✅ 使用以上精確的 Hex 色碼 和 rgb 色碼
- ✅ 嚴格遵循圓角數值
- ❌ 不可使用相近但不同的色碼替代
- ❌ 不可自行添加未在規範中的陰影效果
"""

def get_fallback_design_md() -> str:
    """如果爬取失敗，提供預設設計規範"""
    return """# Fallback Design System

## Visual Theme & Atmosphere
Modern minimalistic interface.

## Color Palette & Roles
| Role | Hex | Usage |
|------|-----|-------|
| Background | #ffffff | 頁面主背景色 |
| Text Primary | #333333 | 主要文字色 |
| Primary Action | #007bff | CTA 按鈕背景色 |
| Input Border | #cccccc | 輸入框邊框顏色 |

## Typography Rules
- **Body Font:** `sans-serif`
- **Heading Font:** `sans-serif`

## Component Stylings
### Buttons
- Border Radius: `4px`
- Box Shadow: `none`
- Padding: `10px 20px`

### Input Fields
- Border Radius: `4px`
- Border Color: `1px solid #cccccc`
- Padding: `10px`
"""

async def get_design_context(url: str) -> dict:
    """
    獲取設計上下文：優先讀取快取，其次即時爬取
    回傳字典：
    {
        "design_md": str,
        "screenshot_b64": str | None,
        "source": "cache" | "live" | "fallback"
    }
    """
    # 1. 嘗試讀取快取
    cached_data = await get_cached_design(url)
    if cached_data:
        design_md = generate_design_md(cached_data)
        return {
            "design_md": design_md,
            "screenshot_b64": cached_data.get("screenshot_base64"),
            "source": "cache"
        }

    # 2. 即時爬取
    extracted_data = await extract_design_tokens(url)
    if extracted_data:
        # 寫入快取
        await set_cached_design(url, extracted_data)
        design_md = generate_design_md(extracted_data)
        return {
            "design_md": design_md,
            "screenshot_b64": extracted_data.get("screenshot_base64"),
            "source": "live"
        }

    # 3. Fallback
    return {
        "design_md": get_fallback_design_md(),
        "screenshot_b64": None,
        "source": "fallback"
    }
