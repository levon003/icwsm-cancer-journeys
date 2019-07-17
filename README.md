Bridging Qualitative and Quantitative Methods for User Modeling: Tracing Cancer Patient Behavior in an Online Health Community
---

Repository for analysis code related to a Spring 2018 study investigating the health journeys of authors on CaringBridge.org.

Originally submitted to ICWSM in January 2019 and accepted July 2019 for presentation at ICWSM 2020.

As described in the paper, CaringBridge data used for analysis is not being released publically for ethical reasons.

For any questions or additional information, contact the corresponding author: levon003@umn.edu

Author website: https://z.umn.edu/zlevonian

### Annotation codebook

Annotation guidance is captured in `annotation_web_client/templates/annotation` in the `phaseTagging.html` and `responsibilityTagging.html` files for cancer phases and patient responsibilities respectively.

### Code organization

Generally, each folder contains an independent analysis.  

`annotation_data` - Utility functions for loading the CaringBridge data alongside the human annotations of that data.

`annotation_web_client` - Contains the code for the web tool used for all annotations.

`classification` - Contains all code related to classification, both ML and keyword based.

`death_analysis` - All code related to sampling additional EOL sites as described in the paper.

`expert_validity` - Analysis of survey administered to expert to check validity of codebook.

`extract_site_features` - Converts raw CaringBridge data to Sqlite or Feather format for easier downstream processing.

`identify_candidate_sites` - Code to identify the set of sites included in this study, to classify author type, and to generate annotation sets.

`journey_phases` - Random analyses related more to the phases, including IRR, etc.

`patient_responsibilities` - Random analyses related more to the responsibilities, including IRR, disagreement discussion, etc.


