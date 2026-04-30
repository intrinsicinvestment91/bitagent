import { types as T, healthUtil } from "../deps.ts";

export const health: T.ExpectedExports.health = {
  async web(effects, duration) {
    return healthUtil
      .checkWebUrl("http://bitagent.embassy:8000/health")(effects, duration)
      .catch(healthUtil.catchError(effects));
  },
};
