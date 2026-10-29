from . import akitashoten, futabasha, hakusensha, kadokawa, kodansha, rakuten, shogakukan, shonengahosha, squareenix, takeshobo

FETCHERS = {
    m.SLUG: m
    for m in (shonengahosha, takeshobo, shogakukan, kodansha, kadokawa, akitashoten, futabasha, hakusensha, squareenix, rakuten)
}
