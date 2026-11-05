export function paginate(items, requestedPage = 1, pageSize = 10) {
 const total=items.length, pageCount=Math.max(1,Math.ceil(total/pageSize));
 const page=Math.max(1,Math.min(pageCount,requestedPage));
 const offset=(page-1)*pageSize;
 return {items:items.slice(offset,offset+pageSize),page,pageCount,total,start:total?offset+1:0,end:Math.min(offset+pageSize,total)};
}
