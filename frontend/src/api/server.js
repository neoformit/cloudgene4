import client from './client'

/** Public server info: name, maintenance, navbar (filtered for the viewer), footer_html. */
export const getServerInfo = () => client.get('/server/')

/** A page from $CLOUDGENE_HOME/pages: `{slug, html}`; 404 if missing. */
export const getPage = (slug) => client.get(`/pages/${encodeURIComponent(slug)}/`)
