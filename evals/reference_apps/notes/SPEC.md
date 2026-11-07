Notes app. People sign up with a username (3-32 letters, digits or underscore) and a password of at least 8 characters,
then log in to get a token. Wrong passwords are rejected, and after 5 failed logins in a minute the account is locked out
for a while. Logged-in users can create notes with a title (1-100 chars) and an optional body (up to 10000 chars).
They can list their notes, search by title, and page through them (default 20, max 100 per page). They can read, edit
and delete a note by id. Each user must only ever see and change their own notes, never anyone else's. Everything except
signup, login and the health check needs a valid token. Errors must not expose internals like stack traces. The service
exposes GET /health returning 200 when it is running and ships in a Docker container.
