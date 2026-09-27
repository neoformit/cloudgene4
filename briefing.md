# Rebuilding the cloudgene application in Python

In the cloudgene3 folder you'll find a Java web application "Cloudgene". Your task is to rebuild the functionality of this application in a Django application with Python.

Core features of the application:

- A web app that allows logged-in users to run Nextflow workflows through a web UI
- Multiple workflows can be hosted on the service, with user access based on group membership
- Workflows run in a job queue such that multiple workflows can be run simultaneously (depending on configuration such as "max queue size")
- Home page, footer, and arbitrary pages (e.g. documentation pages) can be rendered from HTML templates that are easily accessible to developers and admins in the codebase.
- Application configuration in YAML format, to include:
  - Definition of the navbar (masthead) items
  - Definition of installed workflows
  - Definition of each installed workflow, including workflow steps
  - Server settings
- A comprehensive admin panel which exposes:
  - Some general server options (e.g. queue state, queue size, maintenance mode)
  - Status and settings for each workflow (AKA "applications")
  - A jobs page that shows all jobs, their status, and allows admins to cancel jobs
  - A users page that shows all users, their group memberships, and allows admins to edit user group memberships
  - A series of settings pages that allows admins to configure global application settings:
    - General
    - Nextflow
    - Templates
    - Mail
- A user job dashboard that shows the user's jobs and their status, and allows users to cancel their own jobs
- Automatic generation of Nextflow workflow run forms based on workflow definitions in the YAML configuration file
- An interactive, responsive "job status" UI that is shown when a job is submitted, which shows workflow progress in real time, based on the nextflow trace file and other logs.

Finally, there are a few known bugs in the application that should be fixed in the new implementation:

- Sometimes when users register, activate their account and are assigned to a group, we see duplicate user accounts in the admin "Users" view. This is confusing and seems to have caused access issues in the past.
- Sometimes when a workflow is run, it stays in "pending state" forever and has to be killed. This indicates that the queue logic is perhaps not sound.
- If the user enters a space in the "Optional job name" in the job submission form, it causes an error in the backend.
