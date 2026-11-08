"""Keeps the results to news and media sites: social platforms and other non-news hosts are always dropped."""
from .util import domain_of

BLOCK = """facebook.com fb.com fb.watch m.facebook.com instagram.com threads.net youtube.com youtu.be m.youtube.com linkedin.com twitter.com x.com t.co
tiktok.com reddit.com pinterest.com snapchat.com t.me telegram.me telegram.org whatsapp.com wa.me quora.com tumblr.com vk.com weibo.com
discord.com medium.com slideshare.net scribd.com wikipedia.org wikimedia.org play.google.com apps.apple.com amazon.com ebay.com alibaba.com
daraz.com.bd daraz.pk olx.com.bd bikroy.com github.com stackoverflow.com""".split()


def blocked(url, extra=()):
    d = domain_of(url)
    if not d:
        return True
    for b in list(BLOCK) + [x.lower().strip() for x in extra if x]:
        if d == b or d.endswith("." + b):
            return True
    return False


def allowed(url, allow=()):
    """Empty allow-list means every non-blocked site is fine."""
    allow = [a.lower().strip() for a in allow if a and a.strip()]
    if not allow:
        return True
    d = domain_of(url)
    return any(d == a or d.endswith("." + a) for a in allow)
