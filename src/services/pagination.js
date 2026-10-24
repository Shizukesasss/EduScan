export function paginate(items, requestedPage = 1) {
 const total=items.length, pageCount=Math.max(1,Math.ceil(total/10));
 const page=Math.max(1,Math.min(pageCount,requestedPage));
 const offset=(page-1)*10;
 return {items:items.slice(offset,offset+10),page,pageCount,total,start:total?offset+1:0,end:Math.min(offset+10,total)};
}
