# Official OKF example bundle (test fixture)

`acme_retail/` is copied from the official Open Knowledge Format repository:

- source: https://github.com/GoogleCloudPlatform/open-knowledge-format/tree/main/bundles/acme_retail
- commit: ad30107 (2026-10-22)
- license: Apache License 2.0, see [LICENSE.md](LICENSE.md); copyright the original authors

Changes: `viz.html` (a browser visualization, not part of the knowledge) is left out.
All other files are unmodified. The tests check that `okf validate` accepts this bundle
without errors, as the OKF v0.2 conformance rules require.
