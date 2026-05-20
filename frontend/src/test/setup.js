/**
 * Vitest setup file for frontend contract tests
 */

// Global test configuration
global.fetch = fetch
global.Request = Request
global.Response = Response

// Custom matchers for contract testing
expect.extend({
  toBeValidApiResponse(received) {
    const pass = received && typeof received === 'object' && 
                 received.hasOwnProperty('status') && 
                 typeof received.status === 'number'
    
    if (pass) {
      return {
        message: () => `expected ${received} not to be a valid API response`,
        pass: true,
      }
    } else {
      return {
        message: () => `expected ${received} to be a valid API response with status property`,
        pass: false,
      }
    }
  },
  
  toHaveApiField(received, fieldName) {
    const pass = received && typeof received === 'object' && 
                 received.hasOwnProperty(fieldName)
    
    if (pass) {
      return {
        message: () => `expected ${JSON.stringify(received)} not to have field '${fieldName}'`,
        pass: true,
      }
    } else {
      return {
        message: () => `expected ${JSON.stringify(received)} to have field '${fieldName}'`,
        pass: false,
      }
    }
  },
  
  toMatchApiSchema(received, schema) {
    // This will be used with AJV for schema validation
    if (!global.ajv) {
      return {
        message: () => `AJV not initialized for schema validation`,
        pass: false,
      }
    }
    
    const validate = global.ajv.compile(schema)
    const valid = validate(received)
    
    if (valid) {
      return {
        message: () => `expected ${JSON.stringify(received)} not to match schema`,
        pass: true,
      }
    } else {
      return {
        message: () => `expected ${JSON.stringify(received)} to match schema. Errors: ${JSON.stringify(validate.errors)}`,
        pass: false,
      }
    }
  }
})