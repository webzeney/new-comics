from . import shogakukan, shonengahosha, takeshobo

FETCHERS = {m.SLUG: m for m in (shonengahosha, takeshobo, shogakukan)}
