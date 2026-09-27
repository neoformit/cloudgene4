# Repair and restore this broken web application

This project is a Django port of ./cloudgene3/ - an open-source Java application. It appears to be mostly built, but is missing some features and most importantly, has many bugs. In particular, the API and client don't seem to be very well integrated and would have benefitted from a planned implementation declaring API contracts that both could adhere to for compatibility.

There are many unit tests, which seem to pass, yet the application still has many bugs not covered by the tests.

Your task is as follows:

- Review the code and draft a spec for this application, so that we have a context anchor, a list of issues and a list of features to support further development
- Create a series of tasks to bring the application to production-ready robustness
- Create a plan for full agent-driven testing of the app using a headless browser or some other mechanism that allows full testing of the app features with the full stack being tested at once (to identify integration errors). Selenium tests might be more appropriate here - your choice
- Spawn agents to execute each task. Monitor progress, adapt the plans/tasks and update the spec as development progresses
