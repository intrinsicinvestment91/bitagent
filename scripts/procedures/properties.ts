import { types as T } from "../deps.ts";

export const properties: T.ExpectedExports.properties = async (effects) => {
  return {
    result: {
      "API URL": {
        type: "string",
        value: "http://bitagent.embassy:8000",
        description: "Internal BitAgent API endpoint",
        copyable: true,
        qr: false,
        masked: false,
      },
      "API Docs": {
        type: "string",
        value: "http://bitagent.embassy:8000/docs",
        description: "Interactive Swagger API documentation",
        copyable: true,
        qr: false,
        masked: false,
      },
    },
  };
};
