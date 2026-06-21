# API Design Principles
## Description
Design clean, consistent, versioned APIs.
## Instructions
1. Use RESTful conventions: nouns for resources, HTTP verbs for actions
2. Version APIs in URL: /v1/resource
3. Return consistent error format: {error: {code, message, details}}
4. Use proper HTTP status codes (200=OK, 201=Created, 400=BadReq, 404=NotFound, 500=ServerError)
5. Paginate list endpoints: ?offset=0&limit=20
6. Support filtering, sorting, field selection
7. Document with OpenAPI/Swagger
8. Rate limit per client, return 429 with Retry-After header