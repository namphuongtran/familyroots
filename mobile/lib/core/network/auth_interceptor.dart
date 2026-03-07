// TODO: implement in Prompt 2
//
// Dio interceptor that attaches Supabase JWT token to outgoing requests.
//
// - Reads token from Supabase auth session
// - Adds Authorization: Bearer <token> header
// - Handles token refresh on 401 responses
