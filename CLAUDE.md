# Goal
The goal of this project is to create a package of connectivity tools for personal use that I can install via pip or UV into my other Python project environments. This is so that I have a general way of accessing tools like email, text, Google Sheets or Google Calendar, among other things, in a standardized way. 

# Setup
- In general, functional code should be preferred over classes and stateful code in the cases where state is not necessary or in the cases where multiple instances of an object are not required (i.e., there is a singleton that can be accomplished with modules over classes). 
- All code should have a corresponding PyTest which can be used to validate its performance. We should leverage test driven development.
- Sometimes there are multiple ways to access data from a provider, for instance:
    - Service accounts
    - API calls
    - Credentials paired with SMTP protocols
- In general, we should prefer the following when making decisions in regards to access method:
    - Stability of connection: Perpetual authentication that does not expire or require periodic re-authentication
    - Native API: The API is written by the service provider (e.g. native Google packages over smtplib)
    - Free: If possible, free solutions (especially in cases where access to Google services programmatically requires a business account or Google Suite).
- If there are any complicated authentication workflows that should be abstracted away from the user as much as possible, for example if Google requires you to log in and download some JSON credentials and go through an auth workflow, that should be triggered automatically upon first use of the package. The storage of those credentials should be in an app data folder or something similar that is platform agnostic and also stored in such a way that the user doesn't have to worry about it and its whereabouts. It's usage is standardized for the package. 