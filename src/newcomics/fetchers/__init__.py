from . import kadokawa, kodansha, rakuten, shogakukan, shonengahosha, takeshobo

FETCHERS = {m.SLUG: m for m in (shonengahosha, takeshobo, shogakukan, kodansha, kadokawa, rakuten)}
