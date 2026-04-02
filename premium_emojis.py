PREMIUM_EMOJIS = {
  "WOW_FACE": "5769121263079395892",
  "FIRE": "5875093791492282301",
  "KISS": "5908811350645150936",
  "WINK": "5305253958908919472",
  "WAVE": "5413554183502572090",
  "HEART_RED": "5814315039271687782",
  "STAR_GOLD": "5435957248314579621",
  "PLEADING_FACE": "5816896370451157038",
  "CHECK_MARK": "5879898425377428098",
  "CHECK_MARK_ALT": "5875373479762597696",
  "PLANE": "5300866598276450274",
  "GIFT": "5204076520963842994"
}

def get_emoji_tag(emoji_name, fallback_emoji):
  """
  تحويل اسم الملصق إلى وسم HTMتL مع معرف الملصق

  Args:
      emoji_name: اسم الملصق (مثل "FIRE")
      fallback_emoji: الملصق البديل إذا لم يكن المعرف موجوداً

  Returns:
      وسم HTML يحتوي على معرف الملصق المميز
  """
  emoji_id = PREMIUM_EMOJIS.get(emoji_name, "")
  if emoji_id:
      return f"<tg-emoji emoji-id='{emoji_id}'>{fallback_emoji}</tg-emoji>"
  return fallback_emoji
