const surveyResponseRules = {
  fullName: {
    required: true,
    type: "string",
    minLength: 2,
    maxLength: 100
  },
  email: {
    required: true,
    type: "email"
  },
  age: {
    required: true,
    type: "number",
    min: 1,
    max: 120
  },
  role: {
    required: true,
    allowedValues: [
      "student",
      "full-time-job",
      "full-time-learner",
      "prefer-not-to-say",
      "other"
    ]
  },
  recommend: {
    required: true,
    allowedValues: ["definitely", "maybe", "not-sure"]
  },
  favoriteFeature: {
    required: false,
    allowedValues: ["challenges", "projects", "community", "open-source", "other"]
  },
  improvements: {
    required: false,
    type: "array",
    allowedValues: [
      "front-end-projects",
      "back-end-projects",
      "data-visualization",
      "challenges",
      "open-source-community",
      "gitter-help-rooms",
      "videos",
      "city-meetups",
      "wiki",
      "forum",
      "additional-courses"
    ]
  },
  comments: {
    required: true,
    type: "string",
    maxLength: 1000
  }
};

function isValidEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

function validateSurveyResponse(data) {
  const errors = {};

  Object.entries(surveyResponseRules).forEach(([field, rules]) => {
    const value = data[field];

    if (rules.required && (value === undefined || value === null || value === "")) {
      errors[field] = `${field} is required.`;
      return;
    }

    if (value === undefined || value === null || value === "") return;

    if (rules.type === "string" && typeof value !== "string") {
      errors[field] = `${field} must be text.`;
    }

    if (rules.type === "number" && Number.isNaN(Number(value))) {
      errors[field] = `${field} must be a number.`;
    }

    if (rules.type === "email" && !isValidEmail(String(value))) {
      errors[field] = `${field} must be a valid email address.`;
    }

    if (rules.type === "array" && !Array.isArray(value)) {
      errors[field] = `${field} must be a list.`;
    }

    if (rules.minLength && String(value).length < rules.minLength) {
      errors[field] = `${field} must be at least ${rules.minLength} characters.`;
    }

    if (rules.maxLength && String(value).length > rules.maxLength) {
      errors[field] = `${field} must be no more than ${rules.maxLength} characters.`;
    }

    if (rules.min !== undefined && Number(value) < rules.min) {
      errors[field] = `${field} must be at least ${rules.min}.`;
    }

    if (rules.max !== undefined && Number(value) > rules.max) {
      errors[field] = `${field} must be no more than ${rules.max}.`;
    }

    if (rules.allowedValues && !Array.isArray(value) && !rules.allowedValues.includes(value)) {
      errors[field] = `${field} has an invalid value.`;
    }

    if (rules.allowedValues && Array.isArray(value)) {
      const invalidItems = value.filter((item) => !rules.allowedValues.includes(item));
      if (invalidItems.length > 0) {
        errors[field] = `${field} contains invalid values: ${invalidItems.join(", ")}.`;
      }
    }
  });

  return {
    isValid: Object.keys(errors).length === 0,
    errors
  };
}

export { surveyResponseRules, validateSurveyResponse };
