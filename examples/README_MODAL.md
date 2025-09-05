## Usage Examples

This directory contains examples of running `marker` in different contexts.

### Usage with Modal

We have a [self-contained example](./marker_modal_deployment.py) that shows how you can quickly use [Modal](https://modal.com) to deploy `marker` by provisioning a container with a GPU, and expose that with an API so you can submit PDFs for conversion into Markdown, HTML, or JSON.

It's a limited example that you can extend into different use cases.

#### Pre-requisites

Make sure you have the `modal` client installed by [following their instructions here](https://modal.com/docs/guide#getting-started).

Modal's [Starter Plan](https://modal.com/pricing) includes $30 of free compute each month.
Modal is [serverless](https://arxiv.org/abs/1902.03383), so you only pay for resources when you are using them.

#### Running the example

Once `modal` is configured, you can deploy it to your workspace by running:

> modal deploy marker_modal_deployment.py

Notes:
- `marker` has a few models it uses. By default, the endpoint will check if these models are loaded and download them if not (first request will be slow). You can avoid this by running

> modal run marker_modal_deployment.py::download_models

Which will create a [`Modal Volume`](https://modal.com/docs/guide/Volumes) to store them for re-use.

- Regardless, once the deploy is finished, you can submit a request. To do so, get the base URL for your endpoint:
    - Go into Modal
    - Find the app (default name: `datalab-marker-modal-demo`)
    - Click on `MarkerModalDemoService`
    - You should see the URL there

- Make a request to `{BASE_URL}/convert` like this (you can also use Insomnia, etc. to help):
```
curl --request POST \
  --url {BASE_URL}/convert \
  --header 'Content-Type: multipart/form-data' \
  --form file=@/Users/cooldev/sample.pdf \
  --form output_format=html
  ```

You should get a response like this

```
{
	"success": true,
	"filename": "sample.pdf",
	"output_format": "html",
	"json": null,
	"html": "<YOUR_RESPONSE_CONTENT>",
	"markdown": null,
	"images": {},
	"metadata": {... page level metadata ...},
	"page_count": 2
}
```