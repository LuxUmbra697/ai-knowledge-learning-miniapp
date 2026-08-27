## Requirements

### Requirement: User can upload a private document
The system SHALL allow an authenticated user to upload a document file (`.pdf`, `.docx`, `.md`, or `.txt`) to build a personal knowledge base. The system SHALL validate the file extension, file size, and the user's existing document count before accepting the upload.

#### Scenario: Successful upload of a supported format
- **WHEN** an authenticated user uploads a `.pdf`, `.docx`, `.md`, or `.txt` file within size and count limits
- **THEN** the system creates a document record with status `processing`, stores the file temporarily, and immediately returns a `doc_id` without waiting for parsing to complete

#### Scenario: Unsupported file format rejected
- **WHEN** a user uploads a file with an extension other than `.pdf`, `.docx`, `.md`, or `.txt`
- **THEN** the system rejects the upload with a clear error message and does not create any document record

#### Scenario: File exceeds size limit
- **WHEN** a user uploads a file larger than the configured maximum size (default 10MB)
- **THEN** the system rejects the upload with a clear error message

#### Scenario: User exceeds document count limit
- **WHEN** a user who already has the maximum allowed number of documents (default 10) attempts to upload another
- **THEN** the system rejects the upload with a clear error message instructing the user to delete existing documents first

#### Scenario: Unauthenticated upload attempt
- **WHEN** a request without a valid login token attempts to upload a document
- **THEN** the system rejects the request with an authentication error

### Requirement: Document is parsed and embedded asynchronously
The system SHALL asynchronously parse an uploaded document based on its file type, split it into chunks, generate vector embeddings for each chunk, and store them in a per-user vector collection. The system SHALL update the document status to `ready` on success or `failed` with an error message on failure.

#### Scenario: PDF document parsed successfully
- **WHEN** a `.pdf` document finishes background processing without errors
- **THEN** its status becomes `ready` and its chunk count is recorded

#### Scenario: Word document parsed successfully
- **WHEN** a `.docx` document finishes background processing without errors
- **THEN** its status becomes `ready` and its chunk count is recorded

#### Scenario: Markdown or text document parsed successfully
- **WHEN** a `.md` or `.txt` document finishes background processing without errors
- **THEN** its status becomes `ready` and its chunk count is recorded

#### Scenario: Parsing or embedding failure
- **WHEN** document loading, splitting, or embedding raises an exception (e.g. corrupted file, embedding API failure)
- **THEN** the document status becomes `failed`, an error message is recorded, and no partial vectors are left in the vector store for that document

### Requirement: User can query document processing status
The system SHALL allow a user to poll the processing status of their own uploaded document.

#### Scenario: Poll while processing
- **WHEN** a user queries the status of a document that is still being processed
- **THEN** the system returns status `processing`

#### Scenario: Poll after success
- **WHEN** a user queries the status of a document that finished processing successfully
- **THEN** the system returns status `ready` along with its chunk count

#### Scenario: Poll after failure
- **WHEN** a user queries the status of a document that failed processing
- **THEN** the system returns status `failed` along with the error message

#### Scenario: Query another user's document
- **WHEN** a user queries the status of a document owned by a different user
- **THEN** the system returns a not-found error

### Requirement: User can list their own documents
The system SHALL allow an authenticated user to retrieve the list of documents they have uploaded, including filename, status, chunk count, and upload time.

#### Scenario: List documents
- **WHEN** an authenticated user requests their document list
- **THEN** the system returns only documents owned by that user, ordered by most recently uploaded first

### Requirement: User can delete their own document
The system SHALL allow an authenticated user to delete one of their own documents, removing its database record, its vector embeddings, and its stored file.

#### Scenario: Successful deletion
- **WHEN** a user deletes a document they own
- **THEN** the system removes the document's database record, deletes its vectors from the vector store, deletes its stored file, and the document no longer appears in the user's document list

#### Scenario: Delete another user's document
- **WHEN** a user attempts to delete a document owned by a different user
- **THEN** the system rejects the request with a not-found error and does not delete anything

#### Scenario: Partial cleanup failure does not crash the request
- **WHEN** one cleanup step (e.g. deleting the local file) fails during document deletion
- **THEN** the system logs the failure, continues the remaining cleanup steps, and does not return a server error to the client
