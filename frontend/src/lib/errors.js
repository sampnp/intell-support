/** Field -> message from a 422 response (details: [{loc: ["body", "title"], msg}]). */
export function fieldErrors(error) {
  const errors = {};
  if (error?.status !== 422 || !Array.isArray(error.details)) return errors;
  for (const detail of error.details) {
    const field = detail.loc?.[detail.loc.length - 1];
    if (field && !errors[field]) errors[field] = detail.msg;
  }
  return errors;
}
