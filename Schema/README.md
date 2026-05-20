# Schema Folder

This folder contains simple schema files for a Survey Form project.

## Files

- `surveyFormSchema.json` — JSON Schema for defining survey form fields.
- `surveyResponseSchema.json` — JSON Schema for validating submitted survey responses.
- `validationSchema.js` — Lightweight JavaScript validation rules and helper function.
- `exampleResponse.json` — Example response data that follows the response schema.

## Basic usage

Import the JavaScript validator into your form script:

```js
import { validateSurveyResponse } from "./Schema/validationSchema.js";

const result = validateSurveyResponse(formData);

if (!result.isValid) {
  console.log(result.errors);
}
```

You can update the field names and options to match your HTML form inputs.
